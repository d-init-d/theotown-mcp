-- ============================================================================
-- TheoTown Model Context Protocol (MCP) Server
-- Core In-Game Execution Engine & Telemetry Collector
-- Target: plugin/theotown_mcp/core.lua
-- ============================================================================

local script = {}

-- ----------------------------------------------------------------------------
-- Configuration Constants
-- ----------------------------------------------------------------------------
local MAX_WORK_UNITS_PER_TICK = 64      -- Maximum tile/command actions per frame tick
local MAX_TIME_PER_TICK = 0.003         -- 3 milliseconds CPU budget per frame tick
local MAX_ROAD_SEGMENT_TILES = 32       -- Slicing ceiling for road segments
local TELEMETRY_INTERVAL_FRAMES = 60    -- Emit telemetry once per second (~60 FPS)

-- ----------------------------------------------------------------------------
-- State Variables
-- ----------------------------------------------------------------------------
local frame_counter = 0
local last_telemetry_frame = -60
local catalog_exported = false

-- In-memory FIFO queue & active job state machine
local job_queue = {}
local active_job = nil
local processed_job_ids = {}

-- ----------------------------------------------------------------------------
-- Draft Aliases Table
-- ----------------------------------------------------------------------------
local DRAFT_ALIASES = {
    -- Roads
    ["two_lane_road"] = "$road03",
    ["road"] = "$road01",
    ["country_road"] = "$road01",
    ["avenue"] = "$road04",
    ["highway"] = "$road_highway00",
    ["one_way_road"] = "$road02",

    -- Zones
    ["residential_low"] = "$zone_residential_0",
    ["residential_middle"] = "$zone_residential_1",
    ["residential_high"] = "$zone_residential_2",
    ["commercial_low"] = "$zone_commercial_0",
    ["commercial_high"] = "$zone_commercial_1",
    ["industrial_low"] = "$zone_industrial_0",
    ["industrial_high"] = "$zone_industrial_1",

    -- Utilities
    ["pipe"] = "$pipe00",
    ["wire"] = "$wire00"
}

-- ----------------------------------------------------------------------------
-- Helper: Safe Storage & Property Accessors
-- ----------------------------------------------------------------------------
local function getStorage()
    if TheoTown and type(TheoTown.getStorage) == "function" then
        local s = TheoTown.getStorage()
        if s then
            if not s.theotown_mcp_job_status then
                s.theotown_mcp_job_status = {}
            end
            if not s.theotown_mcp_queue then
                s.theotown_mcp_queue = {}
            end
            return s
        end
    end
    return nil
end

local function getDraftProp(d, prop)
    if type(d) == "table" then
        return d[prop]
    elseif type(d) == "userdata" then
        local getter = "get" .. prop:sub(1, 1):upper() .. prop:sub(2)
        if type(d[getter]) == "function" then
            local ok, val = pcall(function() return d[getter](d) end)
            if ok and val ~= nil then return val end
        end
        local ok2, val2 = pcall(function() return d[prop] end)
        if ok2 and val2 ~= nil then return val2 end
    end
    return nil
end

local function resolveDraftId(raw_id, category)
    if not raw_id or raw_id == "" then
        if category == "road" then return "$road03" end
        if category == "pipe" then return "$pipe00" end
        if category == "wire" then return "$wire00" end
        if category == "zone" then return "$zone_residential_0" end
        return raw_id
    end

    -- If draft exists natively, preserve it
    if Draft and type(Draft.getDraft) == "function" then
        local d = Draft.getDraft(raw_id)
        if d ~= nil then return raw_id end
    end

    -- Check alias mapping
    if DRAFT_ALIASES[raw_id] then
        return DRAFT_ALIASES[raw_id]
    end

    return raw_id
end

-- ----------------------------------------------------------------------------
-- Road & Utility Slicing (slices paths > 32 tiles into progressive segments <= 32 tiles)
-- ----------------------------------------------------------------------------
local function sliceRoad(x0, y0, x1, y1, maxTiles)
    maxTiles = maxTiles or MAX_ROAD_SEGMENT_TILES
    local maxSpan = maxTiles - 1 -- Span of 31 grid steps yields 32 tiles inclusive
    local dx = x1 - x0
    local dy = y1 - y0
    local span = math.max(math.abs(dx), math.abs(dy))

    if span <= maxSpan then
        return { { x0 = x0, y0 = y0, x1 = x1, y1 = y1 } }
    end

    local segments = {}
    local num_segments = math.ceil(span / maxSpan)
    for i = 0, num_segments - 1 do
        local t0 = i * maxSpan
        local t1 = math.min((i + 1) * maxSpan, span)
        local sx = math.floor(x0 + (dx * t0) / span + 0.5)
        local sy = math.floor(y0 + (dy * t0) / span + 0.5)
        local ex = (t1 == span) and x1 or math.floor(x0 + (dx * t1) / span + 0.5)
        local ey = (t1 == span) and y1 or math.floor(y0 + (dy * t1) / span + 0.5)
        table.insert(segments, { x0 = sx, y0 = sy, x1 = ex, y1 = ey })
    end
    return segments
end

-- ----------------------------------------------------------------------------
-- Preflight Checks & Pricing Wrappers
-- ----------------------------------------------------------------------------
local function isCityLoaded()
    if not City or type(City.getWidth) ~= "function" then return false end
    local ok, w = pcall(function() return City.getWidth() end)
    return ok and w ~= nil and w > 0
end

local function isCoordInBounds(x, y, w, h)
    if not isCityLoaded() then return true end
    local cw = City.getWidth()
    local ch = City.getHeight()
    w = w or 1
    h = h or 1
    if x < 0 or y < 0 then return false end
    if x + w > cw or y + h > ch then return false end
    return true
end

local function hasSufficientFunds(price)
    if not isCityLoaded() then return true end
    if not price or price <= 0 then return true end
    local ok_sand, is_sand = pcall(function() return City.isSandbox() end)
    if ok_sand and is_sand == true then return true end

    local ok_money, money = pcall(function() return City.getMoney() end)
    if ok_money and type(money) == "number" then
        return money >= price
    end
    return true
end

local function preflightRoad(draft, x0, y0, x1, y1, l0, l1, inner)
    if not isCoordInBounds(x0, y0) or not isCoordInBounds(x1, y1) then
        return false, "Road coordinates out of city bounds", 0
    end
    local price = 0
    if Builder and type(Builder.getRoadPrice) == "function" then
        local ok, p = pcall(function()
            return Builder.getRoadPrice(draft, x0, y0, x1, y1, l0 or 0, l1 or 0, inner or false)
        end)
        if ok and type(p) == "number" then price = p end
    end
    if not hasSufficientFunds(price) then
        return false, "Insufficient funds for road", price
    end
    if Builder and type(Builder.isRoadBuildable) == "function" then
        local ok, res = pcall(function()
            return Builder.isRoadBuildable(draft, x0, y0, x1, y1, l0 or 0, l1 or 0, inner or false)
        end)
        if ok and res == false then
            return false, "Road blocked or unbuildable on terrain", price
        end
    end
    return true, nil, price
end

local function preflightBuilding(draft, x, y, rotation)
    local draftObj = (Draft and type(Draft.getDraft) == "function" and Draft.getDraft(draft)) or nil
    local bw = (draftObj and getDraftProp(draftObj, "width")) or 1
    local bh = (draftObj and getDraftProp(draftObj, "height")) or 1
    if rotation == 1 or rotation == 3 then
        local tmp = bw
        bw = bh
        bh = tmp
    end

    if not isCoordInBounds(x, y, bw, bh) then
        return false, "Building footprint exceeds city bounds", 0
    end

    local price = 0
    if Builder and type(Builder.getBuildingPrice) == "function" then
        local ok, p = pcall(function() return Builder.getBuildingPrice(draft, 1) end)
        if ok and type(p) == "number" then price = p end
    end
    if not hasSufficientFunds(price) then
        return false, "Insufficient funds for building", price
    end
    if Builder and type(Builder.isBuildingBuildable) == "function" then
        local ok, res = pcall(function()
            return Builder.isBuildingBuildable(draft, x, y, rotation or 0)
        end)
        if ok and res == false then
            return false, "Building location obstructed or unbuildable", price
        end
    end
    return true, nil, price
end

local function preflightZone(draft, x, y)
    if not isCoordInBounds(x, y) then
        return false, "Zone tile out of city bounds", 0
    end
    local price = 0
    if Builder and type(Builder.getZonePrice) == "function" then
        local ok, p = pcall(function() return Builder.getZonePrice(draft, 1) end)
        if ok and type(p) == "number" then price = p end
    end
    if not hasSufficientFunds(price) then
        return false, "Insufficient funds for zone", price
    end
    if Builder and type(Builder.isZoneBuildable) == "function" then
        local ok, res = pcall(function() return Builder.isZoneBuildable(draft, x, y) end)
        if ok and res == false then
            return false, "Zone tile blocked by terrain or water", price
        end
    end
    return true, nil, price
end

local function preflightUtility(utilType, draft, x0, y0, x1, y1)
    if not isCoordInBounds(x0, y0) or not isCoordInBounds(x1, y1) then
        return false, "Utility coordinates out of city bounds", 0
    end
    local price = 0
    if utilType == "pipe" then
        if Builder and type(Builder.getPipePrice) == "function" then
            local ok, p = pcall(function() return Builder.getPipePrice(draft, x0, y0, x1, y1) end)
            if ok and type(p) == "number" then price = p end
        end
        if not hasSufficientFunds(price) then
            return false, "Insufficient funds for pipe", price
        end
        if Builder and type(Builder.isPipeBuildable) == "function" then
            local ok, res = pcall(function() return Builder.isPipeBuildable(draft, x0, y0, x1, y1) end)
            if ok and res == false then
                return false, "Pipe cannot be laid along specified path", price
            end
        end
    else
        if Builder and type(Builder.getWirePrice) == "function" then
            local ok, p = pcall(function() return Builder.getWirePrice(draft, x0, y0, x1, y1) end)
            if ok and type(p) == "number" then price = p end
        end
        if not hasSufficientFunds(price) then
            return false, "Insufficient funds for wire", price
        end
        if Builder and type(Builder.isWireBuildable) == "function" then
            local ok, res = pcall(function() return Builder.isWireBuildable(draft, x0, y0, x1, y1) end)
            if ok and res == false then
                return false, "Wire cannot be laid along specified path", price
            end
        end
    end
    return true, nil, price
end

local function preflightDemolish(x, y)
    if not isCoordInBounds(x, y) then
        return false, "Demolish tile out of city bounds", 0
    end
    local price = 0
    if Builder and type(Builder.getRemovePrice) == "function" then
        local ok, p = pcall(function() return Builder.getRemovePrice(x, y) end)
        if ok and type(p) == "number" then price = p end
    end
    if not hasSufficientFunds(price) then
        return false, "Insufficient funds for demolition", price
    end
    if Builder and type(Builder.isRemovable) == "function" then
        local ok, res = pcall(function() return Builder.isRemovable(x, y) end)
        if ok and res == false then
            return false, "Tile contains indestructible object or water", price
        end
    end
    return true, nil, price
end

-- ----------------------------------------------------------------------------
-- Command Decomposition into Atomic Work Units
-- ----------------------------------------------------------------------------
local function decomposeCommand(cmd)
    local units = {}
    local action = cmd.cmd or cmd.action

    if action == "build_road" then
        local x0 = math.floor(cmd.x0 or 0)
        local y0 = math.floor(cmd.y0 or 0)
        local x1 = math.floor(cmd.x1 or 0)
        local y1 = math.floor(cmd.y1 or 0)
        local draft = resolveDraftId(cmd.road_type or cmd.draft or "$road03", "road")
        local level = cmd.level or cmd.level0 or 0

        local slices = sliceRoad(x0, y0, x1, y1, MAX_ROAD_SEGMENT_TILES)
        for _, s in ipairs(slices) do
            table.insert(units, {
                kind = "road",
                draft = draft,
                x0 = s.x0,
                y0 = s.y0,
                x1 = s.x1,
                y1 = s.y1,
                level0 = level,
                level1 = level,
                innerLevels = false
            })
        end

    elseif action == "build_zone" then
        local x = math.floor(cmd.x or 0)
        local y = math.floor(cmd.y or 0)
        local w = math.floor(cmd.width or 1)
        local h = math.floor(cmd.height or 1)
        local draft = resolveDraftId(cmd.zone_type or cmd.draft or "$zone_residential_0", "zone")

        for gx = x, x + w - 1 do
            for gy = y, y + h - 1 do
                table.insert(units, {
                    kind = "zone",
                    draft = draft,
                    x = gx,
                    y = gy
                })
            end
        end

    elseif action == "build_building" then
        local x = math.floor(cmd.x or 0)
        local y = math.floor(cmd.y or 0)
        local draft = resolveDraftId(cmd.building_id or cmd.draft or "", "building")
        local rot = math.floor(cmd.rotation or 0)

        table.insert(units, {
            kind = "building",
            draft = draft,
            x = x,
            y = y,
            rotation = rot
        })

    elseif action == "build_utility" then
        local x0 = math.floor(cmd.x0 or 0)
        local y0 = math.floor(cmd.y0 or 0)
        local x1 = math.floor(cmd.x1 or 0)
        local y1 = math.floor(cmd.y1 or 0)
        local utilType = cmd.utility_type or "pipe"
        local defaultDraft = (utilType == "pipe") and "$pipe00" or "$wire00"
        local draft = resolveDraftId(cmd.draft or defaultDraft, utilType)

        local slices = sliceRoad(x0, y0, x1, y1, MAX_ROAD_SEGMENT_TILES)
        for _, s in ipairs(slices) do
            table.insert(units, {
                kind = "utility",
                utilType = utilType,
                draft = draft,
                x0 = s.x0,
                y0 = s.y0,
                x1 = s.x1,
                y1 = s.y1
            })
        end

    elseif action == "demolish" then
        local x = math.floor(cmd.x or 0)
        local y = math.floor(cmd.y or 0)
        local w = math.floor(cmd.width or 1)
        local h = math.floor(cmd.height or 1)

        for gx = x, x + w - 1 do
            for gy = y, y + h - 1 do
                table.insert(units, {
                    kind = "demolish",
                    x = gx,
                    y = gy
                })
            end
        end

    elseif action == "set_speed" then
        local spd = math.floor(cmd.speed or 1)
        if spd < 0 then spd = 0 end
        if spd > 4 then spd = 4 end
        table.insert(units, {
            kind = "set_speed",
            speed = spd
        })
    end

    return units
end

-- ----------------------------------------------------------------------------
-- Unit Execution Engine
-- ----------------------------------------------------------------------------
local function executeUnit(u, job)
    local isDryRun = job.dry_run or false

    if u.kind == "road" then
        local ok, err, price = preflightRoad(u.draft, u.x0, u.y0, u.x1, u.y1, u.level0, u.level1, u.innerLevels)
        if not ok then
            table.insert(job.errors, err or "Road build error")
            return false
        end
        job.total_spent = (job.total_spent or 0) + price
        if not isDryRun and Builder and type(Builder.buildRoad) == "function" then
            pcall(function()
                Builder.buildRoad(u.draft, u.x0, u.y0, u.x1, u.y1, u.level0, u.level1, u.innerLevels)
            end)
        end
        return true

    elseif u.kind == "building" then
        local ok, err, price = preflightBuilding(u.draft, u.x, u.y, u.rotation)
        if not ok then
            table.insert(job.errors, err or "Building build error")
            return false
        end
        job.total_spent = (job.total_spent or 0) + price
        if not isDryRun and Builder and type(Builder.buildBuilding) == "function" then
            pcall(function()
                Builder.buildBuilding(u.draft, u.x, u.y, u.rotation)
            end)
        end
        return true

    elseif u.kind == "zone" then
        local ok, err, price = preflightZone(u.draft, u.x, u.y)
        if not ok then
            table.insert(job.errors, err or "Zone build error")
            return false
        end
        job.total_spent = (job.total_spent or 0) + price
        if not isDryRun and Builder and type(Builder.buildZone) == "function" then
            pcall(function()
                Builder.buildZone(u.draft, u.x, u.y)
            end)
        end
        return true

    elseif u.kind == "utility" then
        local ok, err, price = preflightUtility(u.utilType, u.draft, u.x0, u.y0, u.x1, u.y1)
        if not ok then
            table.insert(job.errors, err or "Utility build error")
            return false
        end
        job.total_spent = (job.total_spent or 0) + price
        if not isDryRun then
            if u.utilType == "pipe" and Builder and type(Builder.buildPipe) == "function" then
                pcall(function() Builder.buildPipe(u.draft, u.x0, u.y0, u.x1, u.y1) end)
            elseif u.utilType == "wire" and Builder and type(Builder.buildWire) == "function" then
                pcall(function() Builder.buildWire(u.draft, u.x0, u.y0, u.x1, u.y1) end)
            end
        end
        return true

    elseif u.kind == "demolish" then
        local ok, err, price = preflightDemolish(u.x, u.y)
        if not ok then
            table.insert(job.errors, err or "Demolish error")
            return false
        end
        job.total_spent = (job.total_spent or 0) + price
        if not isDryRun and Builder and type(Builder.remove) == "function" then
            pcall(function() Builder.remove(u.x, u.y) end)
        end
        return true

    elseif u.kind == "set_speed" then
        if City and type(City.setSpeed) == "function" then
            pcall(function() City.setSpeed(u.speed) end)
        end
        return true
    end

    return false
end

-- ----------------------------------------------------------------------------
-- Job Status Synchronization
-- ----------------------------------------------------------------------------
local function saveJobStatus(job, status_str)
    local storage = getStorage()
    local err_msg = (#job.errors > 0 and job.errors[1]) or nil

    local status_payload = {
        job_id = job.job_id,
        status = status_str,
        progress = job.progress or 0.0,
        total_steps = job.total_steps or 0,
        completed_steps = job.completed_steps or 0,
        created_at = job.created_at or os.time(),
        updated_at = os.time(),
        error = err_msg,
        result = {
            total_cost = job.total_spent or 0,
            commands_executed = job.completed_steps or 0,
            valid = (#job.errors == 0),
            errors = job.errors
        }
    }

    -- 1. In-memory storage update
    if storage then
        storage.theotown_mcp_job_status[job.job_id] = status_payload
        if status_str == "completed" or status_str == "failed" or status_str == "cancelled" then
            storage.theotown_mcp_last_completed_job = job.job_id
        end
    end

    -- 2. Direct file updates for Python bridge
    if Runtime and type(Runtime.saveText) == "function" and type(Runtime.toJson) == "function" then
        pcall(function()
            local jsonStr = Runtime.toJson(status_payload)
            Runtime.saveText("job_" .. job.job_id .. ".json", jsonStr)
            if storage then
                Runtime.saveText("job_status.json", Runtime.toJson(storage.theotown_mcp_job_status))
            end
        end)
    end
end

-- ----------------------------------------------------------------------------
-- Telemetry Collector
-- ----------------------------------------------------------------------------
function script:emitTelemetry(reason)
    if not isCityLoaded() then return end

    local name = "Unknown"
    pcall(function()
        if City.getName then name = City.getName() end
        if (not name or name == "") and City.getCityName then name = City.getCityName() end
    end)

    local money = 0
    pcall(function() if City.getMoney then money = City.getMoney() end end)

    local population = 0
    pcall(function() if City.getPeople then population = City.getPeople() end end)

    local happiness = 100.0
    if population > 0 then
        pcall(function()
            if City.getHappiness then
                local h = City.getHappiness()
                if type(h) == "number" then happiness = h end
            end
        end)
    end

    local width = 128
    local height = 128
    pcall(function()
        if City.getWidth then width = City.getWidth() end
        if City.getHeight then height = City.getHeight() end
    end)

    local year = 2026
    local month = 1
    local day = 1
    pcall(function()
        if City.getYear then year = City.getYear() end
        if City.getMonth then month = City.getMonth() end
        if City.getDay then day = City.getDay() end
    end)

    local speed = 1
    pcall(function() if City.getSpeed then speed = City.getSpeed() end end)

    local is_sandbox = false
    pcall(function() if City.isSandbox then is_sandbox = City.isSandbox() end end)

    local telemetry = {
        name = name or "City",
        money = money or 0,
        population = population or 0,
        people = population or 0,
        happiness = happiness or 100.0,
        width = width or 128,
        height = height or 128,
        year = year or 2026,
        month = month or 1,
        day = day or 1,
        speed = speed or 1,
        is_sandbox = is_sandbox or false,
        connected = true,
        last_updated = os.time(),
        reason = reason or "PERIODIC",
        frame = frame_counter
    }

    -- Persist to disk via Runtime.saveText
    if Runtime and type(Runtime.saveText) == "function" and type(Runtime.toJson) == "function" then
        pcall(function()
            Runtime.saveText("telemetry.json", Runtime.toJson(telemetry))
        end)
    end

    -- Mirror to shared in-memory bus
    local storage = getStorage()
    if storage then
        storage.theotown_mcp_telemetry = telemetry
    end
end

-- ----------------------------------------------------------------------------
-- Dynamic Draft Catalog Discovery
-- ----------------------------------------------------------------------------
local function discoverAndExportCatalog()
    if not Draft or type(Draft.getDrafts) ~= "function" then return end

    local allDrafts = nil
    local ok, res = pcall(function() return Draft.getDrafts() end)
    if ok and res then allDrafts = res end
    if not allDrafts then return end

    local catalog = {}
    for i = 1, #allDrafts do
        local d = allDrafts[i]
        if d then
            local did = getDraftProp(d, "id")
            if did and did ~= "" then
                local item = {
                    id = did,
                    type = getDraftProp(d, "type") or "building",
                    title = getDraftProp(d, "title") or getDraftProp(d, "name") or did,
                    author = getDraftProp(d, "author") or "Vanilla",
                    price = getDraftProp(d, "price") or 0,
                    monthly_price = getDraftProp(d, "monthlyPrice") or 0,
                    width = getDraftProp(d, "width") or 1,
                    height = getDraftProp(d, "height") or 1
                }
                table.insert(catalog, item)
            end
        end
    end

    if #catalog > 0 and Runtime and type(Runtime.saveText) == "function" and type(Runtime.toJson) == "function" then
        pcall(function()
            local jsonStr = Runtime.toJson(catalog)
            Runtime.saveText("catalog.json", jsonStr)
            Runtime.saveText("drafts.json", jsonStr)
        end)
        catalog_exported = true
    end

    local storage = getStorage()
    if storage then
        storage.theotown_mcp_catalog_count = #catalog
    end
end

-- ----------------------------------------------------------------------------
-- Script Lifecycle Callbacks
-- ----------------------------------------------------------------------------
function script:init()
    local storage = getStorage()
    if storage then
        storage.theotown_mcp_core_version = "1.0.0"
        storage.theotown_mcp_core_ready = true
    end

    -- Discover dynamic draft catalog on startup
    discoverAndExportCatalog()

    -- Emit startup heartbeat
    if Runtime and type(Runtime.saveText) == "function" and type(Runtime.toJson) == "function" then
        pcall(function()
            Runtime.saveText("core_ready.json", Runtime.toJson({
                status = "CORE_READY",
                version = "1.0.0",
                timestamp = os.time()
            }))
        end)
    end
end

function script:enterCity()
    -- Reset transient active state on city switch
    active_job = nil
    job_queue = {}

    -- Immediate telemetry update upon entering active city
    script:emitTelemetry("ENTER_CITY")

    -- Refresh catalog in active city context
    discoverAndExportCatalog()
end

function script:leaveCity()
    active_job = nil
    job_queue = {}
end

-- ----------------------------------------------------------------------------
-- Frame Tick Loop: FIFO Queue & Workload Budgeting (64 units / 3ms per frame)
-- ----------------------------------------------------------------------------
function script:update()
    frame_counter = frame_counter + 1
    local storage = getStorage()

    -- 1. Check for newly deposited job from inbox.lua
    if storage and storage.theotown_mcp_pending_job then
        local raw_job = storage.theotown_mcp_pending_job
        local jid = raw_job.job_id or ("job_" .. os.time())

        -- Duplicate job ID avoidance
        if not processed_job_ids[jid] then
            processed_job_ids[jid] = true

            -- Decompose commands into atomic units
            local units = {}
            if raw_job.commands and type(raw_job.commands) == "table" then
                for _, cmd in ipairs(raw_job.commands) do
                    local cmd_units = decomposeCommand(cmd)
                    for _, u in ipairs(cmd_units) do
                        table.insert(units, u)
                    end
                end
            end

            local new_job = {
                job_id = jid,
                units = units,
                total_steps = #units,
                completed_steps = 0,
                current_unit_index = 1,
                progress = (#units == 0 and 1.0) or 0.0,
                created_at = raw_job.timestamp or raw_job.created_at or os.time(),
                dry_run = raw_job.dry_run or false,
                errors = {},
                total_spent = 0
            }

            table.insert(job_queue, new_job)
            saveJobStatus(new_job, (#units == 0 and "completed") or "pending")
        end

        -- Clear pending mailbox so it isn't re-enqueued
        storage.theotown_mcp_pending_job = nil
    end

    -- 2. Check for mid-execution job cancellation
    if storage and storage.theotown_mcp_cancel_job_id then
        local cancel_id = storage.theotown_mcp_cancel_job_id
        if active_job and active_job.job_id == cancel_id then
            saveJobStatus(active_job, "cancelled")
            active_job = nil
        end
        for i = #job_queue, 1, -1 do
            if job_queue[i].job_id == cancel_id then
                saveJobStatus(job_queue[i], "cancelled")
                table.remove(job_queue, i)
            end
        end
        storage.theotown_mcp_cancel_job_id = nil
    end

    -- 3. Check for catalog refresh requests
    if (storage and storage.theotown_mcp_refresh_catalog) or not catalog_exported then
        discoverAndExportCatalog()
        if storage then storage.theotown_mcp_refresh_catalog = nil end
    end

    -- 4. Periodic telemetry collector (~60 frames = 1 sec)
    if (frame_counter - last_telemetry_frame) >= TELEMETRY_INTERVAL_FRAMES then
        last_telemetry_frame = frame_counter
        script:emitTelemetry("PERIODIC_UPDATE")
    end

    -- 5. Throttled FIFO queue processor: max 64 work units AND 3ms CPU budget
    local start_time = os.clock()
    local units_processed = 0

    while units_processed < MAX_WORK_UNITS_PER_TICK and (os.clock() - start_time) < MAX_TIME_PER_TICK do
        -- Pop next job from FIFO queue if idle
        if not active_job then
            if #job_queue > 0 then
                active_job = table.remove(job_queue, 1)
                -- If job had 0 commands, finish immediately
                if active_job.total_steps == 0 then
                    active_job.progress = 1.0
                    saveJobStatus(active_job, "completed")
                    active_job = nil
                else
                    saveJobStatus(active_job, "running")
                end
            else
                break -- Queue empty, yield tick
            end
        end

        if active_job then
            local u = active_job.units[active_job.current_unit_index]
            if u then
                executeUnit(u, active_job)
                units_processed = units_processed + 1
                active_job.current_unit_index = active_job.current_unit_index + 1
                active_job.completed_steps = active_job.completed_steps + 1
                active_job.progress = active_job.completed_steps / active_job.total_steps

                -- Check if job completed
                if active_job.current_unit_index > active_job.total_steps then
                    local final_status = (#active_job.errors > 0 and active_job.completed_steps == 0) and "failed" or "completed"
                    saveJobStatus(active_job, final_status)
                    active_job = nil
                end
            else
                -- Units exhausted
                saveJobStatus(active_job, "completed")
                active_job = nil
            end
        end
    end
end

return script
