-- TheoTown MCP protocol v2: static Lua engine with a JSON data mailbox.
-- `script` is injected by TheoTown; callbacks must be attached to that object.

local PROTOCOL = 2
local MAX_JOBS = 64
local MAX_COMMANDS = 250
local MAX_UNITS = 10000
local MAX_UNITS_PER_TICK = 16
local MAX_ERROR_DETAILS = 64
local JOB_TTL_SECONDS = 300
local DIAGNOSTICS_INTERVAL_SECONDS = 10
local MAX_COVERAGE_SAMPLES = 512
local MAX_PROBLEM_LOCATIONS = 16
local COVERAGE_THRESHOLD = 0.35

local active = nil
local finished = {}
local loop_started = false
local last_heartbeat = 0
local last_diagnostics = 0
local last_mailbox_error = nil
local diagnostics_error = nil
local cached_diagnostics = nil
local session_id = (Runtime and type(Runtime.getUuid) == "function" and Runtime.getUuid())
  or (tostring(os.time()) .. "-" .. string.gsub(tostring({}), "[^%w]", ""))

local aliases = {
  road = "$road00", two_lane_road = "$road00", dirt_road = "$road01",
  residential_low = "$zoneresidential", residential = "$zoneresidential",
  residential_medium = "$zoneresidential", residential_high = "$zoneresidential_lvl2",
  commercial_low = "$zonecommercial", commercial = "$zonecommercial",
  commercial_medium = "$zonecommercial", commercial_high = "$zonecommercial_lvl2",
  industrial_low = "$zoneindustrial", industrial = "$zoneindustrial",
  industrial_medium = "$zoneindustrial", industrial_high = "$zoneindustrial_lvl2",
  pipe = "$pipe00", wire = "$wire00", park = "$park00", small_park = "$park00",
  fire_station = "$firestation00", police_station = "$policestation00",
  hospital = "$hospital00", school = "$school00"
}

local function now()
  if Runtime and type(Runtime.getTime) == "function" then return Runtime.getTime() / 1000 end
  return os.time()
end

local function call(fn, ...)
  if type(fn) ~= "function" then return false, "API function is unavailable" end
  local ok, value = pcall(fn, ...)
  if not ok then return false, tostring(value) end
  if value == false then return false, "TheoTown rejected the operation" end
  return true, value
end

local function saveJson(name, value)
  if not Runtime or type(Runtime.toJson) ~= "function" or type(Runtime.saveText) ~= "function" then
    return false, "Runtime JSON/file API is unavailable"
  end
  local okEncode, encoded = pcall(Runtime.toJson, value)
  if not okEncode or type(encoded) ~= "string" then return false, tostring(encoded) end
  local okSave, result = pcall(Runtime.saveText, name, encoded)
  if not okSave or result == false then return false, tostring(result) end
  return true
end

local function loadJson(name)
  if not Runtime or type(Runtime.loadText) ~= "function" or type(Runtime.fromJson) ~= "function" then
    return nil, "Runtime JSON/file API is unavailable"
  end
  local okLoad, raw = pcall(Runtime.loadText, name)
  if not okLoad or type(raw) ~= "string" or raw == "" then return nil, tostring(raw) end
  local okDecode, value = pcall(Runtime.fromJson, raw)
  if not okDecode or type(value) ~= "table" then return nil, tostring(value) end
  return value
end

local function optional(owner, name, fallback, ...)
  if owner and type(owner[name]) == "function" then
    local ok, value = pcall(owner[name], ...)
    if ok and value ~= nil then return value end
  end
  return fallback
end

local function cityLoaded()
  return City and type(City.getWidth) == "function" and optional(City, "getWidth", 0) > 0
end

local function invoke(owner, name, fallback, ...)
  if owner and type(owner[name]) == "function" then
    local ok, value = pcall(owner[name], owner, ...)
    if ok and value ~= nil then return value end
  end
  return fallback
end

local function percent(value)
  local number = tonumber(value) or 0
  if number >= 0 and number <= 1 then return number * 100 end
  return number
end

local function countBuildingType(name)
  return optional(City, "countBuildingsOfType", 0, name)
end

local function buildDiagnostics(current)
  local people = {
    low = optional(City, "getPeople", 0, 0),
    middle = optional(City, "getPeople", 0, 1),
    high = optional(City, "getPeople", 0, 2)
  }
  local happinessTypes = {
    health = City and City.HAPPINESS_HEALTH,
    education = City and City.HAPPINESS_EDUCATION,
    fire = City and City.HAPPINESS_FIREDEPARTMENT,
    police = City and City.HAPPINESS_POLICE,
    parks = City and City.HAPPINESS_PARK,
    transport = City and City.HAPPINESS_TRANSPORT,
    supply = City and City.HAPPINESS_SUPPLY,
    taxes = City and City.HAPPINESS_TAXES,
    environment = City and City.HAPPINESS_ENVIRONMENT,
    waste = City and City.HAPPINESS_WASTE,
    leisure = City and City.HAPPINESS_FREETIME
  }
  local happiness = {}
  for name, kind in pairs(happinessTypes) do
    if kind ~= nil then happiness[name] = percent(optional(City, "getHappiness", 0, kind)) end
  end

  local taxes = {}
  local taxTypes = {
    residential = City and City.TAX_RESIDENTIAL,
    commercial = City and City.TAX_COMMERCIAL,
    industrial = City and City.TAX_INDUSTRIAL
  }
  for name, kind in pairs(taxTypes) do
    if kind ~= nil then
      taxes[name .. "_low"] = optional(City, "getTax", 0, kind, 0)
      taxes[name .. "_middle"] = optional(City, "getTax", 0, kind, 1)
      taxes[name .. "_high"] = optional(City, "getTax", 0, kind, 2)
    end
  end

  local infrastructure = {
    buildings = optional(City, "countBuildings", 0),
    roads = optional(City, "countRoads", 0),
    zones = optional(City, "countZones", 0),
    pipes = optional(City, "countPipes", 0),
    wires = optional(City, "countWires", 0),
    cars = optional(City, "countCars", 0),
    energy_buildings = countBuildingType("energy"),
    water_buildings = countBuildingType("water"),
    medical_buildings = countBuildingType("medic"),
    police_buildings = countBuildingType("police"),
    fire_buildings = countBuildingType("fire brigade"),
    education_buildings = countBuildingType("education"),
    parks = countBuildingType("park"),
    waste_buildings = countBuildingType("waste disposal")
  }
  local demand = {
    residential_capacity = optional(City, "getResidentialSpace", 0),
    commercial_jobs = optional(City, "getCommercialJobs", 0),
    industrial_jobs = optional(City, "getIndustrialJobs", 0)
  }

  local coverageTypes = {
    health = Tile and Tile.INFLUENCE_HEALTH,
    police = Tile and Tile.INFLUENCE_POLICE,
    fire = Tile and Tile.INFLUENCE_FIREDEPARTMENT,
    education_low = Tile and Tile.INFLUENCE_EDUCATION_LOW,
    education_high = Tile and Tile.INFLUENCE_EDUCATION_HIGH,
    parks = Tile and Tile.INFLUENCE_PARK,
    waste = Tile and Tile.INFLUENCE_WASTE_DISPOSAL
  }
  local coverage = {}
  for name, kind in pairs(coverageTypes) do
    if kind ~= nil then coverage[name] = { sum = 0, under = 0, samples = 0, weak_locations = {} } end
  end
  local problemCounts = { ill = 0, empty = 0, waste = 0, dead_bodies = 0, burning = 0, no_road = 0 }
  local problemLocations = {}
  local powerProduction, powerConsumption, waterProduction, waterConsumption = 0, 0, 0, 0
  local totalBuildings = infrastructure.buildings
  local sampled = 0

  local function recordProblem(kind, x, y)
    problemCounts[kind] = problemCounts[kind] + 1
    if #problemLocations < MAX_PROBLEM_LOCATIONS then
      problemLocations[#problemLocations + 1] = { type = kind, x = x, y = y }
    end
  end

  for index = 1, totalBuildings do
    local okPosition, x, y = pcall(City.getBuilding, index)
    if okPosition and x ~= nil and y ~= nil then
      local draft = optional(Tile, "getBuildingDraft", nil, x, y)
      if draft ~= nil then
        local performance = tonumber(optional(Tile, "getBuildingPerformance", 1, x, y)) or 1
        local power = tonumber(invoke(draft, "getPower", 0)) or 0
        local water = tonumber(invoke(draft, "getWater", 0)) or 0
        if power >= 0 then powerProduction = powerProduction + power * performance
        else powerConsumption = powerConsumption - power end
        if water >= 0 then waterProduction = waterProduction + water * performance
        else waterConsumption = waterConsumption - water end

        local selected = totalBuildings <= MAX_COVERAGE_SAMPLES
          or math.floor(index * MAX_COVERAGE_SAMPLES / totalBuildings)
             > math.floor((index - 1) * MAX_COVERAGE_SAMPLES / totalBuildings)
        if selected and invoke(draft, "isRCI", false) then
          sampled = sampled + 1
          for name, state in pairs(coverage) do
            local value = tonumber(optional(Tile, "getInfluence", 0, coverageTypes[name], x, y)) or 0
            state.sum = state.sum + value
            state.samples = state.samples + 1
            if value < COVERAGE_THRESHOLD then
              state.under = state.under + 1
              if #state.weak_locations < 8 then
                state.weak_locations[#state.weak_locations + 1] = { x = x, y = y, value_percent = percent(value) }
              end
            end
          end
          if optional(Tile, "isBuildingIll", false, x, y) then recordProblem("ill", x, y) end
          if optional(Tile, "isBuildingEmpty", false, x, y) then recordProblem("empty", x, y) end
          if optional(Tile, "isBuildingFullOfWaste", false, x, y) then recordProblem("waste", x, y) end
          if optional(Tile, "isBuildingFullOfDeadPeople", false, x, y) then recordProblem("dead_bodies", x, y) end
          if optional(Tile, "isBuildingBurning", false, x, y) then recordProblem("burning", x, y) end
          if not optional(Tile, "hasBuildingRoad", true, x, y) then recordProblem("no_road", x, y) end
        end
      end
    end
  end

  for _, state in pairs(coverage) do
    state.average_percent = state.samples > 0 and percent(state.sum / state.samples) or 0
    state.under_threshold_percent = state.samples > 0 and (state.under * 100 / state.samples) or 0
    state.threshold_percent = COVERAGE_THRESHOLD * 100
    state.sum = nil
    state.under = nil
  end
  local function utility(production, consumption)
    return {
      estimated_production = production,
      estimated_consumption = consumption,
      estimated_reserve = production - consumption,
      utilization_percent = production > 0 and consumption * 100 / production or (consumption > 0 and 100 or 0),
      adequate = production >= consumption
    }
  end
  return {
    updated_at = current,
    income = optional(City, "getIncome", 0),
    disaster = optional(City, "getDisaster", nil),
    population_by_level = people,
    happiness_by_category = happiness,
    taxes = taxes,
    demand = demand,
    infrastructure = infrastructure,
    utilities = {
      power = utility(powerProduction, powerConsumption),
      water = utility(waterProduction, waterConsumption)
    },
    service_coverage = coverage,
    problems = {
      sampled_rci_buildings = sampled,
      sample_counts = problemCounts,
      locations = problemLocations
    }
  }
end

local function emitTelemetry(reason)
  if not cityLoaded() then return end
  local current = now()
  if cached_diagnostics == nil or current - last_diagnostics >= DIAGNOSTICS_INTERVAL_SECONDS then
    local ok, value = pcall(buildDiagnostics, current)
    if ok then
      cached_diagnostics = value
      last_diagnostics = current
      diagnostics_error = nil
    else
      diagnostics_error = tostring(value)
    end
  end
  local population = 0
  if City and type(City.getPeople) == "function" then
    population = optional(City, "getPeople", 0, 0) + optional(City, "getPeople", 0, 1) + optional(City, "getPeople", 0, 2)
  end
  local details = cached_diagnostics or {}
  saveJson("telemetry.txt", {
    protocol = PROTOCOL,
    session_id = session_id,
    name = optional(City, "getName", optional(City, "getTitle", "Unknown")),
    money = optional(City, "getMoney", 0),
    population = population,
    people = population,
    income = details.income or optional(City, "getIncome", 0),
    happiness = percent(optional(City, "getHappiness", 100)),
    happiness_by_category = details.happiness_by_category or {},
    population_by_level = details.population_by_level or {},
    demand = details.demand or {},
    taxes = details.taxes or {},
    infrastructure = details.infrastructure or {},
    utilities = details.utilities or {},
    service_coverage = details.service_coverage or {},
    problems = details.problems or {},
    diagnostics_updated_at = details.updated_at or 0,
    diagnostics_error = diagnostics_error,
    width = optional(City, "getWidth", 0),
    height = optional(City, "getHeight", 0),
    year = optional(City, "getYear", 2000),
    month = optional(City, "getMonth", 1),
    day = optional(City, "getDay", 1),
    speed = optional(City, "getSpeed", 1),
    connected = true,
    last_updated = current,
    reason = reason,
    disaster = details.disaster
  })
end

local function validJobId(value)
  return type(value) == "string" and #value >= 1 and #value <= 64 and string.match(value, "^[%w_-]+$") ~= nil
end

local function resolveDraft(raw)
  local id = aliases[raw] or raw
  if type(id) ~= "string" or id == "" then return nil, "Draft id is missing" end
  if not Draft or type(Draft.getDraft) ~= "function" then return nil, "Draft.getDraft is unavailable" end
  local ok, draft = pcall(Draft.getDraft, id)
  if not ok or draft == nil then return nil, "Unknown draft: " .. id end
  return draft
end

local function bounds(x, y)
  x, y = tonumber(tostring(x)), tonumber(tostring(y))
  local width, height = optional(City, "getWidth", 0), optional(City, "getHeight", 0)
  return x ~= nil and y ~= nil and x >= 0 and y >= 0 and x < width and y < height
end

local function addUnit(units, unit)
  if #units >= MAX_UNITS then return false, "Job exceeds 10000 work units" end
  units[#units + 1] = unit
  return true
end

local function describeUnit(unit)
  local kind = tostring(unit.kind or "unknown")
  if unit.x0 ~= nil and unit.y0 ~= nil and unit.x1 ~= nil and unit.y1 ~= nil then
    return string.format("%s (%s,%s)-(%s,%s)", kind, tostring(unit.x0), tostring(unit.y0),
      tostring(unit.x1), tostring(unit.y1))
  end
  if unit.x ~= nil and unit.y ~= nil then
    return string.format("%s (%s,%s)", kind, tostring(unit.x), tostring(unit.y))
  end
  return kind
end

local function recordFailure(job, unit, step, failure)
  local message = tostring(failure)
  job.error_counts = job.error_counts or {}
  job.error_order = job.error_order or {}
  if job.error_counts[message] == nil then
    job.error_counts[message] = 0
    job.error_order[#job.error_order + 1] = message
  end
  job.error_counts[message] = job.error_counts[message] + 1
  if #job.errors < MAX_ERROR_DETAILS then
    job.errors[#job.errors + 1] = string.format("step %d %s: %s", step, describeUnit(unit), message)
  else
    job.omitted_error_details = (job.omitted_error_details or 0) + 1
  end
end

local function summarizeFailures(job)
  local summary = {}
  for _, message in ipairs(job.error_order or {}) do
    local count = job.error_counts[message] or 0
    summary[#summary + 1] = count > 1 and string.format("%dx %s", count, message) or message
  end
  return #summary > 0 and table.concat(summary, "; ") or nil
end

local function expand(job)
  if type(job.commands) ~= "table" then
    return nil, "Commands must be an object"
  end
  local ordered = {}
  for key, command in pairs(job.commands) do
    ordered[#ordered + 1] = { index = tonumber(key) or 1000000, command = command }
  end
  table.sort(ordered, function(a, b) return a.index < b.index end)
  if #ordered > MAX_COMMANDS then return nil, "Commands must contain at most 250 items" end
  local units = {}
  for _, entry in ipairs(ordered) do
    local cmd = entry.command
    if type(cmd) ~= "table" or type(cmd.cmd) ~= "string" then return nil, "Malformed command" end
    if cmd.cmd == "build_zone" or cmd.cmd == "demolish" then
      local width, height = math.floor(cmd.width or 1), math.floor(cmd.height or 1)
      if width < 1 or height < 1 then return nil, "Area dimensions must be positive" end
      for dx = 0, width - 1 do
        for dy = 0, height - 1 do
          local copy = { kind = cmd.cmd, x = cmd.x + dx, y = cmd.y + dy, zone_type = cmd.zone_type }
          local ok, err = addUnit(units, copy)
          if not ok then return nil, err end
        end
      end
    else
      local unit = {}
      for key, value in pairs(cmd) do unit[key] = value end
      unit.kind = cmd.cmd
      local ok, err = addUnit(units, unit)
      if not ok then return nil, err end
    end
  end
  return units
end

local function status(job, state, errorMessage)
  local attempted = job.attempted_steps or 0
  local total = job.total_steps or 0
  local payload = {
    job_id = job.job_id,
    session_id = session_id,
    status = state,
    progress = total == 0 and 1 or attempted / total,
    total_steps = total,
    completed_steps = job.completed_steps or 0,
    attempted_steps = attempted,
    failed_steps = job.failed_steps or 0,
    created_at = job.created_at or now(),
    updated_at = now(),
    error = errorMessage,
    result = { errors = job.errors or {}, error_counts = job.error_counts or {},
               omitted_error_details = job.omitted_error_details or 0,
               commands_executed = job.completed_steps or 0,
               attempted_steps = attempted, failed_steps = job.failed_steps or 0 }
  }
  local ok, err = saveJson("job_" .. job.job_id .. ".txt", payload)
  if not ok then error("Cannot persist job state: " .. tostring(err)) end
end

local function verifyDraft(getterName, x, y, ...)
  if not Tile or type(Tile[getterName]) ~= "function" then return true end
  local ok, result = pcall(Tile[getterName], x, y, ...)
  return ok and result ~= nil
end

local function mutate(fn, ...)
  local ok, result = call(fn, ...)
  if not ok then return false, result end
  return true
end

local function execute(unit)
  if unit.kind == "set_speed" then
    local speed = math.floor(unit.speed or -1)
    if speed < 0 or speed > 4 then return false, "Invalid simulation speed" end
    return mutate(City and City.setSpeed, speed)
  end

  if unit.kind == "build_road" then
    local x0, y0 = tonumber(tostring(unit.x0)), tonumber(tostring(unit.y0))
    local x1, y1 = tonumber(tostring(unit.x1)), tonumber(tostring(unit.y1))
    if not bounds(x0, y0) or not bounds(x1, y1) then return false, "Road is out of bounds" end
    if x0 ~= x1 and y0 ~= y1 then return false, "Road must be horizontal or vertical" end
    local draft, err = resolveDraft(unit.road_type or "$road00")
    if not draft then return false, err end
    local level = math.floor(unit.level or 0)
    local ok, why = call(Builder and Builder.isRoadBuildable, draft, x0, y0, x1, y1, level, level, false)
    if not ok then return false, "Road preflight failed: " .. tostring(why) end
    ok, why = mutate(Builder and Builder.buildRoad, draft, x0, y0, x1, y1, level, level, false)
    if not ok then return false, "Road build failed: " .. tostring(why) end
    if not verifyDraft("getRoadDraft", x0, y0, level) or not verifyDraft("getRoadDraft", x1, y1, level) then
      return false, "Road verification failed"
    end
    return true
  end

  if unit.kind == "build_building" then
    local x, y = tonumber(tostring(unit.x)), tonumber(tostring(unit.y))
    if not bounds(x, y) then return false, "Building is out of bounds" end
    local rotation = math.floor(unit.rotation or 0)
    if rotation < 0 or rotation > 3 then return false, "Rotation must be between 0 and 3" end
    local draft, err = resolveDraft(unit.building_id)
    if not draft then return false, err end
    local ok, why = call(Builder and Builder.isBuildingBuildable, draft, x, y, true, true)
    if not ok then return false, "Building preflight failed: " .. tostring(why) end
    ok, why = mutate(Builder and Builder.buildBuilding, draft, x, y, rotation)
    if not ok then return false, "Building build failed: " .. tostring(why) end
    if not verifyDraft("getBuildingDraft", x, y) then return false, "Building verification failed" end
    return true
  end

  if unit.kind == "build_zone" then
    if not bounds(unit.x, unit.y) then return false, "Zone tile is out of bounds" end
    local draft, err = resolveDraft(unit.zone_type or "residential_low")
    if not draft then return false, err end
    local ok, why = mutate(Builder and Builder.buildZone, draft, unit.x, unit.y)
    if not ok then return false, "Zone build failed: " .. tostring(why) end
    if not verifyDraft("getZoneDraft", unit.x, unit.y) then return false, "Zone verification failed" end
    return true
  end

  if unit.kind == "build_utility" then
    local x0, y0 = tonumber(tostring(unit.x0)), tonumber(tostring(unit.y0))
    local x1, y1 = tonumber(tostring(unit.x1)), tonumber(tostring(unit.y1))
    if not bounds(x0, y0) or not bounds(x1, y1) then return false, "Utility is out of bounds" end
    if x0 ~= x1 and y0 ~= y1 then return false, "Utility must be horizontal or vertical" end
    local utility = unit.utility_type or "pipe"
    local draft, err = resolveDraft(utility)
    if not draft then return false, err end
    local check = utility == "wire" and (Builder and Builder.isWireBuildable) or (Builder and Builder.isPipeBuildable)
    local build = utility == "wire" and (Builder and Builder.buildWire) or (Builder and Builder.buildPipe)
    local ok, why = call(check, draft, x0, y0, x1, y1)
    if not ok then return false, "Utility preflight failed: " .. tostring(why) end
    ok, why = mutate(build, draft, x0, y0, x1, y1)
    if not ok then return false, "Utility build failed: " .. tostring(why) end
    local getter = utility == "wire" and "getWireDraft" or "getPipeDraft"
    if not verifyDraft(getter, x0, y0) or not verifyDraft(getter, x1, y1) then
      return false, "Utility verification failed"
    end
    return true
  end

  if unit.kind == "demolish" then
    if not bounds(unit.x, unit.y) then return false, "Demolition tile is out of bounds" end
    local ok, why = mutate(Builder and Builder.remove, unit.x, unit.y)
    if not ok then return false, "Demolition failed: " .. tostring(why) end
    return true
  end
  return false, "Unsupported command: " .. tostring(unit.kind)
end

local function mailbox()
  local value, loadError = loadJson("requests.txt")
  local problem = nil
  if type(value) ~= "table" then
    problem = "load/decode failed: " .. tostring(loadError) .. " (type=" .. type(value) .. ")"
  elseif tonumber(value.protocol) ~= PROTOCOL then
    problem = "protocol mismatch: " .. tostring(value.protocol)
  elseif type(value.jobs) ~= "table" then
    problem = "jobs is " .. type(value.jobs)
  else
    local count = 0
    for _ in pairs(value.jobs) do count = count + 1 end
    if count > MAX_JOBS then problem = "too many jobs: " .. tostring(count) end
  end
  if problem then
    if problem ~= last_mailbox_error then
      saveJson("mailbox_error.txt", { error = problem, updated_at = now() })
      last_mailbox_error = problem
    end
    return nil
  end
  last_mailbox_error = nil
  return value
end

local function cancelRequested(jobId)
  local box = mailbox()
  if not box then return false end
  local item = box.jobs[jobId]
  if type(item) == "table" then return item.cancel_requested == true end
  return false
end

local function acquire()
  local box = mailbox()
  if not box then return nil end
  local candidate = nil
  for id, job in pairs(box.jobs) do
    if type(job) == "table" and job.job_id == id and validJobId(id) and not finished[id] then
      if not candidate or (job.created_at or 0) < (candidate.created_at or 0) then candidate = job end
    end
  end
  local job = candidate
  if job then
      if job.session_id ~= session_id then
        job.total_steps, job.errors, job.error_counts, job.error_order = 0, {}, {}, {}
        status(job, "failed", "Job belongs to a different TheoTown city session")
        finished[job.job_id] = true
      elseif now() - (job.created_at or 0) > JOB_TTL_SECONDS then
        job.total_steps, job.errors, job.error_counts, job.error_order = 0, {}, {}, {}
        status(job, "failed", "Job expired before execution")
        finished[job.job_id] = true
      elseif job.cancel_requested == true then
        job.total_steps, job.errors, job.error_counts, job.error_order = 0, {}, {}, {}
        status(job, "cancelled", nil)
        finished[job.job_id] = true
      else
        local old = loadJson("job_" .. job.job_id .. ".txt")
        if old and old.status == "running" then
          job.total_steps, job.errors, job.error_counts, job.error_order = old.total_steps or 0, {}, {}, {}
          status(job, "failed", "Plugin restarted during execution; job will not be replayed")
          finished[job.job_id] = true
        elseif old and (old.status == "completed" or old.status == "failed" or old.status == "cancelled") then
          finished[job.job_id] = true
        else
          local units, err = expand(job)
          if not units then
            job.total_steps, job.errors, job.error_counts, job.error_order = 0, {}, {}, {}
            status(job, "failed", err)
            finished[job.job_id] = true
          else
            job.units, job.index, job.errors = units, 1, {}
            job.error_counts, job.error_order, job.omitted_error_details = {}, {}, 0
            job.total_steps, job.attempted_steps = #units, 0
            job.completed_steps, job.failed_steps = 0, 0
            status(job, "running", nil)
            return job
          end
        end
      end
  end
  return nil
end

local function runWork()
  if not active then active = acquire() end
  if not active then return end
  if cancelRequested(active.job_id) then
    status(active, "cancelled", nil)
    finished[active.job_id], active = true, nil
    return
  end
  local count = 0
  while active and count < MAX_UNITS_PER_TICK do
    local unit = active.units[active.index]
    if not unit then
      local final = active.failed_steps > 0 and "failed" or "completed"
      local message = summarizeFailures(active)
      status(active, final, message)
      finished[active.job_id], active = true, nil
      break
    end
    local ok, err = execute(unit)
    active.attempted_steps = active.attempted_steps + 1
    if ok then active.completed_steps = active.completed_steps + 1
    else
      active.failed_steps = active.failed_steps + 1
      recordFailure(active, unit, active.index, err)
    end
    active.index = active.index + 1
    count = count + 1
  end
  if active then status(active, "running", nil) end
end

local function tick()
  local ok, err = pcall(function()
    local current = now()
    if current - last_heartbeat >= 1 then
      emitTelemetry("ACTIVE_CITY")
      last_heartbeat = current
    end
    runWork()
  end)
  if not ok and Runtime and type(Runtime.saveText) == "function" then
    pcall(Runtime.saveText, "core_error.txt", tostring(err))
  end
end

local function scheduledTick()
  tick()
  if Runtime and type(Runtime.postpone) == "function" then Runtime.postpone(scheduledTick, 100) end
end

function script:update()
  if not loop_started then tick() end
end

function script:init()
  pcall(function()
    saveJson("core_ready.txt", { protocol = PROTOCOL, session_id = session_id, status = "CORE_READY", updated_at = now() })
    emitTelemetry("PLUGIN_INIT")
    if Runtime and type(Runtime.postpone) == "function" then
      loop_started = true
      Runtime.postpone(scheduledTick, 100)
    end
  end)
end
