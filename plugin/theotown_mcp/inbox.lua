-- ============================================================================
-- TheoTown MCP: Hot-Reload Command Mailbox (#LuaWrapper)
-- Target: plugin/theotown_mcp/inbox.lua
-- Watched by #LuaWrapper (dev: true). Re-executed automatically on file change.
-- ============================================================================

local script = {}

-- Retrieve global in-memory state bus
local storage = nil
if TheoTown and type(TheoTown.getStorage) == "function" then
    storage = TheoTown.getStorage()
end

-- Template job definition placeholder (populated by Python bridge or left idle)
local pending_job = nil

-- Deposit job into storage bus if present
if storage and pending_job ~= nil then
    storage.theotown_mcp_pending_job = pending_job
end

-- Emit inbox acknowledgment receipt
if Runtime and type(Runtime.saveText) == "function" and type(Runtime.toJson) == "function" then
    local ack_payload = {
        status = (pending_job and "JOB_DEPOSITED") or "INBOX_READY",
        job_id = (pending_job and pending_job.job_id) or "NONE",
        timestamp = os.time(),
        reloaded_at = os.time()
    }
    pcall(function()
        Runtime.saveText("inbox_ack.json", Runtime.toJson(ack_payload))
    end)
end

function script:init()
    if storage then
        if pending_job ~= nil then
            storage.theotown_mcp_pending_job = pending_job
        end
    end
end

return script
