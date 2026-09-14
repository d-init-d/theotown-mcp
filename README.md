# TheoTown MCP Server (`theotown-mcp`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP SDK v2](https://img.shields.io/badge/MCP%20SDK-v2.2.0-green.svg)](https://modelcontextprotocol.io/)

A production-grade **Model Context Protocol (MCP)** server bridging AI agents (Claude Desktop, Cursor IDE, Hermes Agent, Antigravity) to the **TheoTown** city simulation game. It empowers AI models to inspect city states, design urban layouts, and construct road networks, buildings, zones, and utilities through the official TheoTown Lua API and a durable JSON mailbox.

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
                  Atomic JSON Write (%USERPROFILE%\TheoTown\plugins\)
                                       v
+--------------------------------------------------------------------------------+
|                    DATA MAILBOX (requests.txt, protocol v2)                    |
|  - Cross-process lock plus atomic read-modify-write updates                    |
|  - Up to 64 concurrent queued jobs without command loss                       |
|  - Session binding, cancellation flags, TTL, and replay protection            |
+--------------------------------------------------------------------------------+
                                       |
                         Periodic mailbox polling
                                       v
+--------------------------------------------------------------------------------+
|                       CORE ENGINE (plugin/theotown_mcp/core.lua)               |
|  - Static startup script with a protocol-v2 execution engine                  |
|  - Durable job lifecycle with per-session anti-replay safeguards              |
|  - Workload throttling (max 16 work units per 100 ms tick)                    |
|  - Official Builder preflight checks plus post-build Tile verification        |
|  - Bounded, coordinate-aware failure details and live telemetry               |
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
3. **Durable Enqueue**: Python appends the validated command to `requests.txt` under a cross-process lock, then commits the JSON with a same-directory atomic replace and bounded Windows retry loop.
4. **Session Safety**: Every job is tied to the active city session. Expired, replayed, or cross-city jobs fail closed instead of executing in the wrong save.
5. **Queue & Budgeting**: `core.lua` polls the mailbox, expands area operations into work units, and processes at most 16 units every 100 ms so large plans do not freeze the game.
6. **Telemetry & Feedback**: TheoTown writes protocol-v2 heartbeats to `telemetry.txt` and bounded job results to `job_<job_id>.txt`; MCP clients can poll progress or cancel pending work.

---

### 2. Prerequisites & Installation

#### Requirements
- Windows 10/11 (AMD64)
- Python 3.10 or higher (Python 3.11+ recommended)
- TheoTown (Steam or standalone) installed at `%USERPROFILE%\TheoTown`

#### Installation Steps
```powershell
# Option A: Install from Wheel (Production Package)
python -m hatchling build
pip install dist/theotown_mcp-0.2.0-py3-none-any.whl

# Option B: Clone & Install in Editable Mode (Development)
git clone https://github.com/d-init-d/theotown-mcp.git
cd theotown-mcp
pip install -e .

# 3. Deploy in-game Lua plugin non-destructively
theotown-mcp install-plugin

# 4. Verify IPC and storage communication
theotown-mcp probe-ipc
```

> **Note on Initial Discovery**: TheoTown discovers newly created plugin folders when the game starts. If TheoTown was running when you ran `install-plugin`, restart the game once. After startup, `core.lua` consumes new jobs as JSON data without modifying or executing Lua source files.

---

### 3. Guardrails, Batch Limits & Job Lifecycle

- **Batch Safeguards**:
  - Maximum commands per plan: **250 commands**.
  - Maximum affected tiles per plan: **10,000 tiles**.
  - Strict coordinate validation: `x >= 0, y >= 0`, strictly bounded by the active city's width and height.
- **Job Lifecycle**:
  - `pending`: Durably queued in `requests.txt` for the active city session.
  - `running`: Actively being executed in-game across frame ticks.
  - `completed`: All work units successfully placed.
  - `failed`: Any work unit failed (e.g. obstruction, terrain, insufficient funds), with structured error messages and step counts (`attempted_steps`, `completed_steps`, `failed_steps`).
  - `cancelled`: Aborted via `theotown_cancel_job`.

---

### 4. Client Configurations

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

### 5. API Reference

#### Tools (12 Tools)
| Tool Name | Parameters | Description |
|---|---|---|
| `theotown_get_status` | *None* | Get current city status (money, population, happiness, dimensions, speed, date). |
| `theotown_build_road` | `x0`, `y0`, `x1`, `y1`, `road_type`, `level` | Construct a horizontal or vertical road between two coordinates. |
| `theotown_build_zone` | `x`, `y`, `width`, `height`, `zone_type` | Designate a rectangular zone (residential, commercial, industrial). |
| `theotown_build_building` | `x`, `y`, `building_id`, `rotation` | Construct a specific building draft by ID or friendly alias. |
| `theotown_build_utilities` | `x0`, `y0`, `x1`, `y1`, `utility_type` | Place a horizontal or vertical pipe or wire. TheoTown may reject occupied, water, or unsuitable tiles. |
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
- **Cầu nối tệp tin nguyên tử (`bridge.py`)**: Ghi dữ liệu JSON vào `requests.txt` bằng khóa liên tiến trình, tệp tạm cùng thư mục, `fsync` và `os.replace` có thử lại khi Windows tạm khóa tệp.
- **Hộp thư giao thức v2**: Giữ tối đa 64 tác vụ, gắn mỗi tác vụ với phiên thành phố hiện tại, hỗ trợ TTL, hủy có xác nhận và chống phát lại sau khi plugin khởi động lại.
- **Bộ điều phối `core.lua`**: Đọc hộp thư định kỳ, xử lý tối đa 16 đơn vị công việc mỗi 100 ms, dùng API `Builder` chính thức để kiểm tra/xây và API `Tile` để xác nhận kết quả.
- **Phản hồi có giới hạn**: Kết quả lưu số bước thành công/thất bại, tối đa 64 lỗi mẫu có tọa độ và bảng đếm lỗi, tránh làm phình file hoặc phản hồi MCP.

---

### 2. Cài Đặt & Khởi Chạy

#### Yêu cầu hệ thống
- Hệ điều hành: Windows 10 hoặc 11 (AMD64)
- Python: 3.10 trở lên
- Trò chơi TheoTown (Steam hoặc bản độc lập) cài đặt tại `%USERPROFILE%\TheoTown`

#### Các bước cài đặt
```powershell
# Cách A: Cài đặt từ gói Wheel phân phối (Production)
python -m hatchling build
pip install dist/theotown_mcp-0.2.0-py3-none-any.whl

# Cách B: Cài đặt ở chế độ phát triển (Editable Development)
git clone https://github.com/d-init-d/theotown-mcp.git
cd theotown-mcp
pip install -e .

# 3. Cài đặt plugin Lua an toàn vào thư mục plugins của TheoTown
theotown-mcp install-plugin

# 4. Kiểm tra đường truyền giao tiếp IPC
theotown-mcp probe-ipc
```

> **Lưu ý**: Lần đầu tiên sau khi cài đặt plugin bằng lệnh `theotown-mcp install-plugin`, hãy khởi động lại TheoTown một lần để game nạp `core.lua`. Sau đó plugin nhận tác vụ mới dưới dạng dữ liệu JSON mà không cần sửa hoặc thực thi mã Lua động.

---

### 3. Cơ Chế Bảo Vệ, Giới Hạn & Trạng Thái Tác Vụ

- **Giới Hạn An Toàn**:
  - Tối đa **250 lệnh** cho mỗi kế hoạch (plan).
  - Tối đa **10,000 ô** diện tích ảnh hưởng cho mỗi kế hoạch.
  - Tọa độ nghiêm ngặt: `x >= 0, y >= 0`, giới hạn chính xác theo kích thước bản đồ hiện tại.
- **Vòng Đời Tác Vụ (Job Lifecycle)**:
  - `pending`: Đã được ghi bền vững vào `requests.txt` cho đúng phiên thành phố.
  - `running`: Đang được game thực thi từng bước theo khung hình tick.
  - `completed`: Toàn bộ các bước xây dựng thành công 100%.
  - `failed`: Có bước gặp lỗi (vướng địa hình, thiếu tiền...), lưu vết chi tiết `attempted_steps`, `completed_steps`, `failed_steps` và danh sách lỗi.
  - `cancelled`: Đã hủy thành công qua lệnh `theotown_cancel_job`.

---

### 4. Hướng Dẫn Cấu Hình Cho Các Nền Tảng AI

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

### 5. Danh Sách Công Cụ & Tài Nguyên

- **Công cụ xây dựng & quản trị (12 Tools)**:
  - `theotown_get_status`: Lấy thông tin tài chính, dân số, độ hạnh phúc, kích thước bản đồ và tốc độ game.
  - `theotown_build_road`: Xây đường ngang hoặc dọc giữa hai tọa độ với draft và cao độ chỉ định.
  - `theotown_build_zone`: Quy hoạch các khu dân cư, thương mại, công nghiệp.
  - `theotown_build_building`: Đặt công trình theo ID hoặc tên gọi đại diện (alias).
  - `theotown_build_utilities`: Đặt ống nước hoặc dây điện theo đường ngang/dọc; game có thể từ chối ô đã bị chiếm, ô nước hoặc địa hình không phù hợp.
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

### 6. Kiểm Thử Tự Động (Testing)

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
