# TheoTown MCP Server (`theotown-mcp`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP SDK v2](https://img.shields.io/badge/MCP%20SDK-v2.2.0-green.svg)](https://modelcontextprotocol.io/)

A production-grade **Model Context Protocol (MCP)** server bridging AI agents (Claude Desktop, Cursor IDE, Hermes Agent, Antigravity) to the **TheoTown** city simulation game. It empowers AI models to inspect city states, design urban layouts, and construct road networks, buildings, zones, and utilities via the official TheoTown Lua API and `#LuaWrapper` hot-reload IPC.

---

> **Ngôn ngữ / Languages:** [English](#english) | [Tiếng Việt](#tiếng-việt)

---

<a name="english"></a>
## English Documentation

### 1. Architecture & IPC Flow

`theotown-mcp` connects AI agent reasoning to TheoTown's in-game engine without requiring game client restarts or simulated UI mouse clicks:

```
+--------------------------------------------------------------------------------+
|                                AI AGENT RUNTIME                                |
|             (Claude Desktop / Cursor IDE / Hermes / Antigravity)               |
+--------------------------------------------------------------------------------+
                                       |
                   MCP JSON-RPC Protocol (stdio / streamable-http)
                                       v
+--------------------------------------------------------------------------------+
|                        PYTHON MCP SERVER (src/theotown_mcp)                    |
|  - MCPServer v2: 12 Tools, 2 Resources, 1 Prompt                               |
|  - Two-Layer Validation (Pydantic Schema + Dynamic City Bounds)                |
|  - Offline / Dynamic Catalog & Price Estimation                                |
|  - Hardened Windows Atomic Bridge (same-dir temp file + fsync + os.replace)   |
+--------------------------------------------------------------------------------+
                                       |
                   Atomic File Write (%USERPROFILE%\TheoTown\plugins\)
                                       v
+--------------------------------------------------------------------------------+
|                     INBOX MAILBOX (plugin/theotown_mcp/inbox.lua)              |
|  - Watched by TheoTown's #LuaWrapper with "dev": true                          |
|  - Instantly hot-reloads on file timestamp change                              |
|  - Stores payload into TheoTown.getStorage().theotown_mcp_pending_job          |
+--------------------------------------------------------------------------------+
                                       |
                      In-Memory Lua State Bus (TheoTown.getStorage())
                                       v
+--------------------------------------------------------------------------------+
|                       CORE ENGINE (plugin/theotown_mcp/core.lua)               |
|  - Persistent startup script (does not reload, maintains state)                |
|  - FIFO Queue Manager & Job Lifecycle State Machine                            |
|  - Workload Budgeting & Throttling (max 64 tiles / 3ms per frame tick)         |
|  - Road Segmenting (slices paths > 32 tiles with shared boundary joints)       |
|  - Preflight validation (Builder.is*Buildable) & Cost checks (get*Price)       |
|  - Telemetry generation & Dynamic Draft Catalog Discovery                      |
+--------------------------------------------------------------------------------+
                                       |
                      Official TheoTown Lua Engine APIs
                                       v
+--------------------------------------------------------------------------------+
|                           THEOTOWN SIMULATION WORLD                            |
|             (City, Builder, Draft, Tile, Runtime Libraries)                    |
+--------------------------------------------------------------------------------+
```

#### Detailed IPC Sequence
1. **Tool Invocation**: An AI client invokes an MCP tool (e.g. `theotown_build_road` or `theotown_execute_plan`).
2. **Two-Layer Validation**:
   - **Schema Layer**: Pydantic v2 ensures non-negative coordinates, positive dimensions, and valid elevation.
   - **Runtime Layer**: Python checks current city bounds (`City.getWidth()`, `City.getHeight()`).
3. **Atomic Lua Serialization**: Payload is serialized to Lua table format with string escaping (`serialize_to_lua()`). Written to a co-located temporary file, flushed, fsynced, closed, and atomically replaced (`os.replace`) with an exponential backoff retry loop absorbing transient Windows file locks (`[WinError 32]`).
4. **Hot-Reload Trigger**: `#LuaWrapper` with `"dev": true` detects `inbox.lua` update and evaluates it within ~16ms without game restart.
5. **Queue & Budgeting**: `core.lua` picks up pending jobs from `TheoTown.getStorage()`, decomposes operations into atomic work units, and processes them within the budget (max 64 tiles / 3ms per tick) inside `script:update()`, guaranteeing smooth frame rates without engine watchdog stutters.
6. **Telemetry & Feedback**: Simulation updates are written to `telemetry.json` and mirrored in shared memory.

---

### 2. Prerequisites & Installation

#### Requirements
- Windows 10/11 (AMD64)
- Python 3.10 or higher (Python 3.11+ recommended)
- TheoTown (Steam or standalone) installed at `%USERPROFILE%\TheoTown`

#### Installation Steps
```powershell
# 1. Clone the repository
git clone https://github.com/d-init-d/theotown-mcp.git
cd theotown-mcp

# 2. Install Python package in editable mode
pip install -e .

# 3. Deploy in-game Lua plugin to TheoTown
theotown-mcp install-plugin

# 4. Verify IPC and storage communication
theotown-mcp probe-ipc
```

> **Note on Initial Discovery**: TheoTown discovers newly created plugin folders when the game starts. If TheoTown was running when you ran `install-plugin`, restart the game once. Once loaded, all subsequent commands hot-reload dynamically with zero restarts.

---

### 3. Client Configurations

#### Claude Desktop
Add to `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "theotown": {
      "command": "theotown-mcp",
      "args": ["run", "--transport", "stdio"],
      "env": {
        "THEOTOWN_DATA_DIR": "C:\\Users\\<USERNAME>\\TheoTown"
      }
    }
  }
}
```

#### Cursor IDE
Add to `.cursor/mcp.json` or Cursor Settings -> Features -> MCP:
```json
{
  "mcpServers": {
    "theotown": {
      "command": "theotown-mcp",
      "args": ["run", "--transport", "stdio"]
    }
  }
}
```

#### Hermes Agent
In your Hermes agent configuration file (`hermes.yaml` or `config.json`):
```yaml
mcp_servers:
  theotown:
    command: theotown-mcp
    args:
      - run
      - --transport
      - stdio
    env:
      THEOTOWN_DATA_DIR: "%USERPROFILE%\\TheoTown"
```

#### Streamable HTTP Transport (Remote / Containerized)
You can also run the server over HTTP:
```powershell
theotown-mcp run --transport http --port 8000
```
Then connect clients to `http://127.0.0.1:8000/mcp`.

---

### 4. API Reference

#### Tools (12 Tools)
| Tool Name | Parameters | Description |
|---|---|---|
| `theotown_get_status` | *None* | Get current city status (money, population, happiness, dimensions, speed, date). |
| `theotown_build_road` | `x0`, `y0`, `x1`, `y1`, `road_type`, `level` | Construct a road between two coordinates. Slices roads > 32 tiles automatically. |
| `theotown_build_zone` | `x`, `y`, `width`, `height`, `zone_type` | Designate a rectangular zone (residential, commercial, industrial). |
| `theotown_build_building` | `x`, `y`, `building_id`, `rotation` | Construct a specific building draft by ID or friendly alias. |
| `theotown_build_utilities` | `x0`, `y0`, `x1`, `y1`, `utility_type`, `level` | Place utility lines (pipe or wire) between two coordinates. |
| `theotown_demolish` | `x`, `y`, `width`, `height` | Demolish buildings, zones, or terrain across a rectangular area. |
| `theotown_validate_plan` | `commands`, `dry_run` | Validate an entire multi-step urban plan without modifying the game world. |
| `theotown_execute_plan` | `commands` | Enqueue a multi-step batch plan for staged execution. |
| `theotown_get_job` | `job_id` | Check the progress and status of an enqueued or running job. |
| `theotown_cancel_job` | `job_id` | Cancel a running or pending construction job mid-flight. |
| `theotown_set_speed` | `speed` (`0`=Pause, `1`=Normal, `2`=Fast, `3`=Super, `4`=Ultra) | Change the game simulation speed. |
| `theotown_get_draft_catalog` | `category`, `query` | Search and list available drafts (roads, buildings, zones) and friendly aliases. |

#### Resources (2 Resources)
| URI | MIME Type | Description |
|---|---|---|
| `theotown://city/status` | `application/json` | Real-time live city telemetry feed. |
| `theotown://catalog/drafts` | `application/json` | Complete cached draft catalog metadata and alias mappings. |

#### Prompts (1 Prompt)
| Prompt Name | Description |
|---|---|
| `urban_planner` | System instructions for AI agents on city planning principles, road hierarchy, RCI zoning ratios, and utility layout. |

---

<a name="tiếng-việt"></a>
## Tiếng Việt (Vietnamese Documentation)

### 1. Kiến Trúc & Luồng Truyền Thông IPC

`theotown-mcp` kết nối trực tiếp khả năng lập luận của các AI Agent tới game mô phỏng đô thị **TheoTown** mà không cần khởi động lại game hay giả lập click chuột trên màn hình:

- **Python MCP Server (`src/theotown_mcp`)**: Xây dựng trên chuẩn MCP SDK v2 (`MCPServer`), cung cấp 12 công cụ (tools), 2 tài nguyên (resources) và 1 prompt hướng dẫn quy hoạch đô thị.
- **Cầu nối tệp tin nguyên tử (Atomic Filesystem IPC Bridge - `bridge.py`)**: Ghi mã nguồn Lua vào `inbox.lua` thông qua quy trình tạo tệp tạm cùng ổ đĩa, flush, fsync và `os.replace` có cơ chế thử lại (exponential retry) chống xung đột khóa tệp trên Windows (`[WinError 32]`).
- **Trình nạp nóng `#LuaWrapper`**: `plugin.json` cấu hình `dev: true` trên `inbox.lua`, giúp TheoTown tự động phát hiện thay đổi tệp tin và thực thi ngay lập tức trong máy ảo JVM Luaj (~16ms).
- **Bộ điều phối tác vụ `core.lua`**: Duy trì hàng đợi FIFO, điều tiết giới hạn tải (tối đa 64 ô / 3ms mỗi khung hình tick) để đảm bảo game không bị giật lag, tự động cắt các đoạn đường dài hơn 32 ô thành các phân đoạn liên tục có khớp nối và gửi dữ liệu đo lường (telemetry) về thành phố.

---

### 2. Cài Đặt & Khởi Chạy

#### Yêu cầu hệ thống
- Hệ điều hành: Windows 10 hoặc 11 (AMD64)
- Python: 3.10 trở lên
- Trò chơi TheoTown (Steam hoặc bản độc lập) cài đặt tại `%USERPROFILE%\TheoTown`

#### Các bước cài đặt
```powershell
# 1. Tải mã nguồn dự án
git clone https://github.com/d-init-d/theotown-mcp.git
cd theotown-mcp

# 2. Cài đặt package Python ở chế độ editable
pip install -e .

# 3. Cài đặt plugin Lua vào thư mục plugins của TheoTown
theotown-mcp install-plugin

# 4. Kiểm tra đường truyền giao tiếp IPC
theotown-mcp probe-ipc
```

> **Lưu ý**: Lần đầu tiên sau khi cài đặt plugin bằng lệnh `theotown-mcp install-plugin`, hãy khởi động lại trò chơi TheoTown một lần để game quét và nạp thư mục plugin mới. Từ các lần sau, mọi lệnh xây dựng của AI sẽ được cập nhật nóng tức thì mà không cần khởi động lại.

---

### 3. Hướng Dẫn Cấu Hình Cho Các Nền Tảng AI

#### Claude Desktop
Mở tệp cấu hình tại `%APPDATA%\Claude\claude_desktop_config.json` và thêm:
```json
{
  "mcpServers": {
    "theotown": {
      "command": "theotown-mcp",
      "args": ["run", "--transport", "stdio"],
      "env": {
        "THEOTOWN_DATA_DIR": "C:\\Users\\<TÊN_USER>\\TheoTown"
      }
    }
  }
}
```

#### Cursor IDE
Thêm vào `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "theotown": {
      "command": "theotown-mcp",
      "args": ["run", "--transport", "stdio"]
    }
  }
}
```

#### Hermes Agent
Thêm vào tệp cấu hình `hermes.yaml`:
```yaml
mcp_servers:
  theotown:
    command: theotown-mcp
    args:
      - run
      - --transport
      - stdio
```

---

### 4. Danh Sách Công Cụ & Tài Nguyên

- **Công cụ xây dựng & quản trị (12 Tools)**:
  - `theotown_get_status`: Lấy thông tin tài chính, dân số, độ hạnh phúc, kích thước bản đồ và tốc độ game.
  - `theotown_build_road`: Xây dựng mạng lưới đường bộ, tự động chia nhỏ đoạn dài > 32 ô.
  - `theotown_build_zone`: Quy hoạch các khu dân cư, thương mại, công nghiệp.
  - `theotown_build_building`: Đặt công trình theo ID hoặc tên gọi đại diện (alias).
  - `theotown_build_utilities`: Đặt hệ thống ống dẫn nước và dây điện.
  - `theotown_demolish`: Giải phóng mặt bằng, phá dỡ công trình hoặc đường sá.
  - `theotown_validate_plan`: Kiểm tra trước tính hợp lệ và ước lượng chi phí của kế hoạch quy hoạch mà không làm thay đổi bản đồ.
  - `theotown_execute_plan`: Đưa một danh sách lệnh vào hàng đợi để xây dựng dần theo khung hình.
  - `theotown_get_job`: Kiểm tra tiến độ hoàn thành của tác vụ.
  - `theotown_cancel_job`: Hủy tác vụ xây dựng đang thực thi.
  - `theotown_set_speed`: Điều chỉnh tốc độ mô phỏng game (0: Tạm dừng, 1: Bình thường, 2: Nhanh, 3: Siêu nhanh, 4: Cực nhanh).
  - `theotown_get_draft_catalog`: Tra cứu danh mục mẫu công trình, đường xá và các bí danh thân thiện.

- **Tài nguyên (Resources)**:
  - `theotown://city/status`: Dữ liệu trạng thái thành phố theo thời gian thực (JSON).
  - `theotown://catalog/drafts`: Danh mục toàn bộ các bản thiết kế (drafts) trong game.

- **Prompt Hướng Dẫn**:
  - `urban_planner`: Hướng dẫn chuyên sâu cho AI về nguyên lý quy hoạch mạng lưới giao thông hình học, cân đối tỷ lệ phân vùng RCI và tối ưu hóa hạ tầng điện nước.

---

### 5. Kiểm Thử Tự Động (Testing)

Để chạy toàn bộ bộ kiểm thử tự động (Unit Tests & End-to-End Suite):
```powershell
# Chạy toàn bộ pytest
pytest

# Hoặc sử dụng runner chuyên dụng cho E2E
python tests/e2e/runner.py --tier all
```

---

## License

Dự án được phát hành theo giấy phép [MIT License](LICENSE). Bản quyền © 2026 TheoTown MCP Team.
