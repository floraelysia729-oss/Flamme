# Flamme 竞赛产品实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Flamme 从 Obsidian 插件扩展为独立 Web/PWA 竞赛产品，包含知识图谱可视化、苏格拉底提问、盲区发现、间隔重复、结构化笔记五大核心能力。

**Architecture:** Svelte 5 + Vite 前端通过 HTTP/SSE 对接已有 FastAPI 后端。后端新增四个工具模块和两个路由。SQLite 新增 entity_reviews 和 activity_log 表。

**Tech Stack:** Svelte 5 · Vite · D3 force · FastAPI · SQLite · OpenAI SDK (DeepSeek)

**执行策略：** 后端先行 → 前端交互设计 → 前端实现

---

## Phase 1: 后端扩展（当前阶段）

在 2.0 后端基础上新增功能模块和 API 端点。所有改动在 3.0 仓库中进行。

### 新增后端文件

```
src/
├── api/routes/
│   ├── activity.py           # 活跃数据 + 热力图 API
│   └── review.py             # 间隔重复 API
├── tools/
│   ├── socratic.py           # 苏格拉底提问
│   ├── gap_detection.py      # 盲区发现
│   ├── spaced_rep.py         # SM-2 算法
│   └── note_generator.py     # 结构化笔记生成
├── db/
│   └── review_store.py       # 复习进度 DB 层
```

### 修改的后端文件

```
src/db/schema.sql             # 新增 entity_reviews + activity_log 表
src/db/client.py              # 新增 activity/review 相关方法
src/api/app.py                # 注册新路由
src/agent/orchestrator.py     # 集成 socratic 模式
src/api/routes/graph.py       # 新增 /path, /entity/{name}/card, /gaps 端点
src/api/routes/ingest.py      # 新增 /upload multipart 端点
```

---

### Task 1: DB Schema — activity_log + entity_reviews

**Files:**
- Modify: `src/db/schema.sql`

- [ ] **1.1** 在 `src/db/schema.sql` 末尾追加两张表

```sql
-- 活跃日志
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER REFERENCES entities(id),
    action TEXT NOT NULL CHECK(action IN ('created','reviewed','linked','gap_filled')),
    source_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(date(created_at));
CREATE INDEX IF NOT EXISTS idx_activity_entity ON activity_log(entity_id);

-- 间隔重复
CREATE TABLE IF NOT EXISTS entity_reviews (
    entity_id INTEGER PRIMARY KEY REFERENCES entities(id),
    review_count INTEGER DEFAULT 0,
    ease_factor REAL DEFAULT 2.5,
    interval_days INTEGER DEFAULT 1,
    last_reviewed_at DATE,
    next_review_at DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **1.2** 验证 schema 可执行

```bash
cd D:\dev\LLM-WIKI\3.0
python -c "
import sqlite3, pathlib
schema = pathlib.Path('src/db/schema.sql').read_text()
conn = sqlite3.connect(':memory:')
conn.executescript(schema)
print('Schema OK — tables:', [r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall()])
"
```

- [ ] **1.3** 提交

```bash
git add src/db/schema.sql
git commit -m "feat(db): activity_log + entity_reviews 表"
```

---

### Task 2: ingest/upload 端点

**Files:**
- Modify: `src/api/routes/ingest.py`

Web 端需要上传文件，现有 `POST /api/ingest` 只接受 vault 内路径。

- [ ] **2.1** 读取当前 `src/api/routes/ingest.py`，在末尾新增 upload 端点

```python
from fastapi import UploadFile, File
import os

@router.post("/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    request: Request = None,
):
    """Web 端文件上传 → 保存到 vault → 触发 ingest"""
    cfg = get_request_config_or_default(request)
    vault = cfg.vault_path

    # 保存上传文件到 vault/pro/upload/
    dest_dir = os.path.join(vault, "pro", "upload")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, file.filename)
    with open(dest, "wb") as f:
        f.write(await file.read())

    # 触发现有 ingest 流程
    rel_path = os.path.relpath(dest, vault).replace("\\", "/")
    from src.api.agent_registry import AgentRegistry
    agent = AgentRegistry(cfg).get_agent()
    result = agent.run(f'ingest "{rel_path}"', level="pro")

    return {"status": "ok", "path": rel_path, "result": result}
```

> **注意：** 需要根据 `ingest.py` 实际的 import 和 helper 函数调整。`get_request_config_or_default` 已在该文件中 import。`AgentRegistry` 的调用方式需确认现有模式。

- [ ] **2.2** 验证端点注册成功

```bash
python -c "from src.api.app import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'upload' in r or 'ingest' in r])"
```

- [ ] **2.3** 提交

```bash
git add src/api/routes/ingest.py
git commit -m "feat(api): POST /api/ingest/upload Web 文件上传端点"
```

---

### Task 3: 结构化笔记生成 (note_generator.py)

**Files:**
- Create: `src/tools/note_generator.py`

- [ ] **3.1** 创建 `src/tools/note_generator.py`

```python
"""根据实体名 + 来源内容生成结构化学习笔记。"""

NOTE_GEN_PROMPT = """你是一个知识整理助手。根据以下实体的相关内容，生成结构化学习笔记。

实体名：{entity_name}
类型：{entity_type}
相关内容：
{source_content}

请生成 JSON 格式的笔记（缺内容的板块留空字符串）：
{{
  "concept": "核心定义与直觉理解（1-3 句）",
  "core": "关键公式/定理，用 LaTeX 语法（如 $$f(x)$$），无公式则留空",
  "methods": "解题技巧/对比总结/方法速通，可用 markdown 表格",
  "sources": "来自哪份资料哪一页",
  "gaps": "该实体可能缺少但应该关联的概念，用顿号分隔"
}}
"""

class NoteGenerator:
    def __init__(self, llm=None):
        self.llm = llm

    def generate(self, entity_name: str, entity_type: str, source_content: str) -> dict:
        if not self.llm:
            return {"concept": "", "core": "", "methods": "", "sources": "", "gaps": ""}

        prompt = NOTE_GEN_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            source_content=source_content[:3000],
        )
        resp = self.llm.complete([{"role": "user", "content": prompt}])
        import json
        try:
            text = resp.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return {"concept": resp[:200], "core": "", "methods": "", "sources": "", "gaps": ""}
```

- [ ] **3.2** 提交

```bash
git add src/tools/note_generator.py
git commit -m "feat(tools): 结构化笔记生成器 NoteGenerator"
```

---

### Task 4: Entity Card API

**Files:**
- Modify: `src/api/routes/graph.py`

- [ ] **4.1** 在 `src/api/routes/graph.py` 新增 `GET /entity/{name:path}/card` 端点

> **注意：** 需要先读取 graph.py 了解现有 `_graph_store(cfg)` helper 和 `_to_force_graph_format` 的写法，保持一致。

```python
@router.get("/entity/{name:path}/card")
def get_entity_card(name: str, request: Request):
    """返回实体的结构化学习卡片"""
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)

    # 1. 获取实体基本信息
    node = store.get_node_by_name(name)
    if not node:
        return {"error": f"Entity '{name}' not found"}

    # 2. 获取邻居（关联节点）
    neighbors = store.get_neighbors(name)
    neighbor_names = [n["name"] for n in neighbors.get("nodes", [])]

    # 3. 读取实体文件内容
    import os
    source_content = ""
    wiki_path = node.get("wiki_path") or node.get("entity_file", "")
    if wiki_path:
        full_path = os.path.join(cfg.vault_path, wiki_path)
        if os.path.isfile(full_path):
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                source_content = f.read()[:3000]

    # 4. 生成结构化笔记
    from src.tools.note_generator import NoteGenerator
    from src.llm.provider import LLMProvider
    llm = LLMProvider(cfg)
    gen = NoteGenerator(llm)
    note = gen.generate(name, node.get("type", "concept"), source_content)

    # 5. 查找盲区
    gaps = []
    if note.get("gaps"):
        for gap_name in note["gaps"].split("、"):
            gap_name = gap_name.strip()
            if gap_name and gap_name not in neighbor_names:
                gaps.append({"target": gap_name, "reason": "内容提到但图谱中未连接"})

    return {
        "name": name,
        "type": node.get("type", ""),
        "concept": note.get("concept", ""),
        "core": note.get("core", ""),
        "methods": note.get("methods", ""),
        "sources": note.get("sources", ""),
        "gaps": gaps,
        "related_nodes": neighbor_names,
    }
```

- [ ] **4.2** 同文件新增 `GET /path` 端点（对话联动路径高亮用）

```python
@router.get("/path")
def get_path(source: str, target: str, request: Request):
    """两实体间最短路径"""
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    result = store.shortest_path(source, target)
    if not result:
        return {"path": [], "hops": 0}
    return {"path": result, "hops": len(result) - 1}
```

- [ ] **4.3** 提交

```bash
git add src/api/routes/graph.py
git commit -m "feat(api): GET /graph/entity/{name}/card + /graph/path"
```

---

### Task 5: 苏格拉底提问 (socratic.py)

**Files:**
- Create: `src/tools/socratic.py`

- [ ] **5.1** 创建 `src/tools/socratic.py`

```python
"""基于用户知识图谱盲区的苏格拉底式提问。"""

SOCRATIC_PROMPT = """你是一位苏格拉底式导师。你的职责是：
1. 绝不直接给出答案
2. 用问题引导学生思考
3. 基于学生的知识结构提问

当前实体：{entity_name}
学生已掌握的关联概念：{known_concepts}
学生图谱中缺失的连接：{missing_links}

请生成 1-2 个苏格拉底式问题，引导学生发现缺失的知识连接。
返回 JSON：{{"questions": ["问题1", "问题2"], "hints": ["提示1", "提示2"]}}
"""

class SocraticGenerator:
    def __init__(self, llm=None):
        self.llm = llm

    def generate(self, entity_name: str, known: list[str], missing: list[str]) -> dict:
        if not self.llm:
            fallback_q = f"你觉得{entity_name}和{missing[0]}之间有什么关系？" if missing else f"用自己的话解释一下{entity_name}"
            return {"questions": [fallback_q], "hints": []}

        prompt = SOCRATIC_PROMPT.format(
            entity_name=entity_name,
            known_concepts="、".join(known) or "无",
            missing_links="、".join(missing) or "无",
        )
        resp = self.llm.complete([{"role": "user", "content": prompt}])
        import json
        try:
            text = resp.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return {"questions": [resp], "hints": []}
```

- [ ] **5.2** 提交

```bash
git add src/tools/socratic.py
git commit -m "feat(tools): 苏格拉底提问生成器 SocraticGenerator"
```

---

### Task 6: Orchestrator 苏格拉底模式

**Files:**
- Modify: `src/agent/orchestrator.py`

- [ ] **6.1** 在 `orchestrator.py` 的 overlay 常量区域（`SEARCH_OVERLAY` / `LEARN_OVERLAY` 附近）新增

```python
SOCRATIC_OVERLAY = """\n你现在处于**苏格拉底教学模式**。

核心规则：
- 绝不直接给出答案
- 每次回复都必须包含至少一个引导性问题
- 参考学生的知识图谱结构（已知概念和缺失连接）
- 如果学生回答正确，追问更深层的理解
- 如果学生回答错误，用反例或类比引导纠正
- 适当表扬学生的思考过程

参考学生的图谱盲区来设计问题，帮助他们发现自己知识中的缺口。"""
```

- [ ] **6.2** 在 `chat()` 方法的 mode overlay 选择逻辑处新增分支

```python
elif mode == "socratic":
    system_prompt += SOCRATIC_OVERLAY
```

> **注意：** 需要确认现有 mode 分支写法。当前有 `search` 和 `learn` 两种模式，在 `chat()` 方法中通过 if/elif 选择 overlay。

- [ ] **6.3** 提交

```bash
git add src/agent/orchestrator.py
git commit -m "feat(agent): 苏格拉底对话模式 SOCRATIC_OVERLAY"
```

---

### Task 7: Activity API + Client 方法

**Files:**
- Modify: `src/db/client.py`
- Create: `src/api/routes/activity.py`
- Modify: `src/api/app.py`

- [ ] **7.1** 在 `src/db/client.py` 的 `SQLiteClient` 类中新增方法

```python
def log_activity(self, entity_id: int, action: str, source_file: str = ""):
    """记录活跃日志"""
    self._conn.execute(
        "INSERT INTO activity_log (entity_id, action, source_file) VALUES (?, ?, ?)",
        (entity_id, action, source_file),
    )
    self._conn.commit()

def get_heatmap(self, year: int = 0) -> list[dict]:
    """返回每日活动计数 [{date, count}]"""
    import datetime
    y = year or datetime.date.today().year
    rows = self._conn.execute("""
        SELECT date(created_at) as day, COUNT(*) as cnt
        FROM activity_log
        WHERE strftime('%Y', created_at) = ?
        GROUP BY day ORDER BY day
    """, (str(y),)).fetchall()
    return [{"date": r[0], "count": r[1]} for r in rows]
```

- [ ] **7.2** 创建 `src/api/routes/activity.py`

```python
from fastapi import APIRouter, Request
from src.api.deps import get_request_config_or_default

router = APIRouter(prefix="/activity", tags=["activity"])

@router.get("/heatmap")
def heatmap(year: int = 0, request: Request = None):
    cfg = get_request_config_or_default(request)
    db = get_db(cfg)
    return db.get_heatmap(year)

@router.get("/day")
def day_activity(date: str, request: Request = None):
    cfg = get_request_config_or_default(request)
    db = get_db(cfg)
    rows = db._conn.execute("""
        SELECT a.action, a.source_file, e.name
        FROM activity_log a JOIN entities e ON a.entity_id = e.id
        WHERE date(a.created_at) = ?
    """, (date,)).fetchall()
    return {"date": date, "entities": [{"name": r[2], "action": r[0], "source": r[1]} for r in rows]}

@router.get("/summary")
def summary(request: Request = None):
    cfg = get_request_config_or_default(request)
    db = get_db(cfg)
    import datetime
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    row = db._conn.execute("""
        SELECT COUNT(DISTINCT entity_id) as ents,
               COUNT(DISTINCT source_file) as files
        FROM activity_log WHERE date(created_at) >= ?
    """, (week_ago,)).fetchone()
    return {"week_entities": row[0], "week_files": row[1]}
```

> **注意：** `get_db(cfg)` 的调用方式需确认 `deps.py` 中已有的 DB 获取方法。当前代码用 `SQLiteClient(cfg.db_path)` 创建实例。

- [ ] **7.3** 在 `src/api/app.py` 注册路由

```python
from src.api.routes import activity
app.include_router(activity.router)
```

- [ ] **7.4** 提交

```bash
git add src/db/client.py src/api/routes/activity.py src/api/app.py
git commit -m "feat(api): 活跃数据 API — 热力图 + 日详情 + 周摘要"
```

---

### Task 8: SM-2 间隔重复 + Review API

**Files:**
- Create: `src/tools/spaced_rep.py`
- Create: `src/db/review_store.py`
- Create: `src/api/routes/review.py`
- Modify: `src/api/app.py`

- [ ] **8.1** 创建 `src/tools/spaced_rep.py`

```python
"""SM-2 间隔重复算法。"""

from datetime import date, timedelta

def sm2(review_count: int, ease_factor: float, interval: int, quality: int) -> dict:
    """
    quality: 0-5 (0=完全忘记, 5=完美记忆)
    返回: {ease_factor, interval_days, next_review: date}
    """
    if quality < 3:
        return {
            "ease_factor": max(1.3, ease_factor - 0.2),
            "interval_days": 1,
            "next_review": date.today() + timedelta(days=1),
        }

    new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)

    if review_count == 0:
        new_interval = 1
    elif review_count == 1:
        new_interval = 6
    else:
        new_interval = round(interval * new_ef)

    return {
        "ease_factor": new_ef,
        "interval_days": new_interval,
        "next_review": date.today() + timedelta(days=new_interval),
    }
```

- [ ] **8.2** 创建 `src/db/review_store.py`

```python
import sqlite3
from datetime import date, timedelta

class ReviewStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_due_reviews(self, today: str = None) -> list[dict]:
        d = today or date.today().isoformat()
        rows = self.conn.execute("""
            SELECT er.entity_id, e.name, er.next_review_at, er.review_count
            FROM entity_reviews er JOIN entities e ON er.entity_id = e.id
            WHERE date(er.next_review_at) <= ?
            ORDER BY er.next_review_at
        """, (d,)).fetchall()
        return [{"entity_id": r[0], "entity_name": r[1], "next_review": r[2], "review_count": r[3]} for r in rows]

    def record_review(self, entity_id: int, ease_factor: float, interval_days: int, next_review: str):
        today = date.today().isoformat()
        self.conn.execute("""
            INSERT INTO entity_reviews (entity_id, review_count, ease_factor, interval_days, last_reviewed_at, next_review_at)
            VALUES (?, 1, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                review_count = review_count + 1,
                ease_factor = excluded.ease_factor,
                interval_days = excluded.interval_days,
                last_reviewed_at = excluded.last_reviewed_at,
                next_review_at = excluded.next_review_at
        """, (entity_id, ease_factor, interval_days, today, next_review))
        self.conn.commit()

    def get_or_create(self, entity_id: int) -> dict:
        row = self.conn.execute("SELECT entity_id, review_count, ease_factor, interval_days, next_review_at FROM entity_reviews WHERE entity_id = ?", (entity_id,)).fetchone()
        if row:
            return {"entity_id": row[0], "review_count": row[1], "ease_factor": row[2], "interval_days": row[3], "next_review_at": row[4]}
        next_r = (date.today() + timedelta(days=1)).isoformat()
        self.conn.execute("INSERT INTO entity_reviews (entity_id, next_review_at) VALUES (?, ?)", (entity_id, next_r))
        self.conn.commit()
        return {"entity_id": entity_id, "review_count": 0, "ease_factor": 2.5, "interval_days": 1, "next_review_at": next_r}
```

- [ ] **8.3** 创建 `src/api/routes/review.py`

```python
from fastapi import APIRouter, Request
from pydantic import BaseModel
from src.api.deps import get_request_config_or_default
from src.db.review_store import ReviewStore
from src.tools.spaced_rep import sm2

router = APIRouter(prefix="/review", tags=["review"])

class ReviewRequest(BaseModel):
    quality: int  # 0-5

@router.get("/due")
def due_reviews(request: Request):
    cfg = get_request_config_or_default(request)
    from src.db.client import SQLiteClient
    db = SQLiteClient(cfg.db_path)
    store = ReviewStore(db._conn)
    return store.get_due_reviews()

@router.post("/{entity_id}")
def record_review(entity_id: int, body: ReviewRequest, request: Request):
    cfg = get_request_config_or_default(request)
    from src.db.client import SQLiteClient
    db = SQLiteClient(cfg.db_path)
    store = ReviewStore(db._conn)
    current = store.get_or_create(entity_id)
    result = sm2(current["review_count"], current["ease_factor"], current["interval_days"], body.quality)
    store.record_review(entity_id, result["ease_factor"], result["interval_days"], result["next_review"].isoformat())
    return {"status": "ok", **result}
```

- [ ] **8.4** 在 `src/api/app.py` 注册路由

```python
from src.api.routes import review
app.include_router(review.router)
```

- [ ] **8.5** 提交

```bash
git add src/tools/spaced_rep.py src/db/review_store.py src/api/routes/review.py src/api/app.py
git commit -m "feat(api): 间隔重复 SM-2 + /api/review 端点"
```

---

### Task 9: 盲区检测 (gap_detection.py + gaps 端点)

**Files:**
- Create: `src/tools/gap_detection.py`
- Modify: `src/api/routes/graph.py`

- [ ] **9.1** 创建 `src/tools/gap_detection.py`

```python
"""知识图谱盲区检测：找到应该连接但未连接的实体对。"""

GAP_VALIDATION_PROMPT = """你是一个知识关联分析专家。

以下是用户知识图谱中的两个实体，它们之间没有直接的连接。
请判断它们是否应该有关联。

实体 A：{source}（类型：{source_type}）
实体 B：{target}（类型：{target_type}）
A 的已知关联：{source_neighbors}
B 的已知关联：{target_neighbors}

返回 JSON：{{"should_connect": true/false, "reason": "为什么应该/不应该连接", "relation_type": "建议的关系类型"}}
"""

class GapDetector:
    def __init__(self, graph_store, llm=None):
        self.store = graph_store
        self.llm = llm

    def detect_gaps(self, max_suggestions: int = 10) -> list[dict]:
        """检测知识图谱中的盲区"""
        # 1. 获取完整图谱
        full = self.store.get_full_graph()

        # 2. 构建邻接集
        existing_edges = set()
        neighbor_map: dict[str, list[str]] = {}
        for e in full["edges"]:
            key = tuple(sorted([e["source"], e["target"]]))
            existing_edges.add(key)
            neighbor_map.setdefault(e["source"], []).append(e["target"])
            neighbor_map.setdefault(e["target"], []).append(e["source"])

        # 3. 同一 community 内未连接的实体对
        communities: dict[int, list[str]] = {}
        for n in full["nodes"]:
            c = n.get("community", -1)
            if c >= 0:
                communities.setdefault(c, []).append(n["name"])

        candidates = []
        for c, members in communities.items():
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    key = tuple(sorted([a, b]))
                    if key not in existing_edges:
                        candidates.append({"source": a, "target": b, "community": c})

        # 4. LLM 验证候选对
        if self.llm and candidates:
            validated = []
            for pair in candidates[:max_suggestions * 3]:
                try:
                    result = self._validate_pair(pair, neighbor_map)
                    if result and result.get("should_connect"):
                        validated.append({
                            "source": pair["source"],
                            "target": pair["target"],
                            "reason": result["reason"],
                            "confidence": 0.8,
                            "relation_type": result.get("relation_type", "related"),
                        })
                except Exception:
                    continue
                if len(validated) >= max_suggestions:
                    break
            return validated

        # 无 LLM：返回低置信度候选
        return [
            {"source": c["source"], "target": c["target"], "reason": "同一知识群落内未连接", "confidence": 0.4}
            for c in candidates[:max_suggestions]
        ]

    def _validate_pair(self, pair, neighbor_map):
        if not self.llm:
            return None
        prompt = GAP_VALIDATION_PROMPT.format(
            source=pair["source"], source_type="concept",
            target=pair["target"], target_type="concept",
            source_neighbors="、".join(neighbor_map.get(pair["source"], [])) or "无",
            target_neighbors="、".join(neighbor_map.get(pair["target"], [])) or "无",
        )
        resp = self.llm.complete([{"role": "user", "content": prompt}])
        import json
        try:
            text = resp.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return None
```

- [ ] **9.2** 在 `src/api/routes/graph.py` 新增 `GET /gaps` 端点

```python
@router.get("/gaps")
def detect_gaps(request: Request):
    """检测知识图谱盲区"""
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    from src.tools.gap_detection import GapDetector
    detector = GapDetector(store)
    return detector.detect_gaps()
```

- [ ] **9.3** 提交

```bash
git add src/tools/gap_detection.py src/api/routes/graph.py
git commit -m "feat(tools): 知识盲区检测 — 同 community 未连接实体对 + LLM 验证"
```

---

## Phase 2: 前端交互设计（待执行）

> 后端完成后，进入前端交互设计阶段。产出物为每个视图的详细交互 spec，包含：
> - 信息架构和布局 wireframe
> - 状态流转（空 / 加载 / 有数据 / 错误）
> - 交互动效规格
> - 组件层级和 props 接口
> - 响应式策略
>
> 设计完成后重写 Phase 3 的 tasks。

**设计范围：**

| 视图 | 关键设计点 |
|------|-----------|
| 图谱视图 | D3 力导向布局、节点点击侧滑面板、盲区虚线、导入流程、空状态 |
| 活跃视图 | 热力图 grid、日详情展开、待复习列表 |
| 对话视图 | SSE 流式渲染、搜索/苏格拉底模式切换、图谱联动高亮 |
| 全局 | Tab 导航、像素火苗三场景、苹果风组件库 |

---

## Phase 3: 前端实现（待 Phase 2 完成后重写）

> 前端 tasks 将根据 Phase 2 的交互设计稿拆分，每个 task 对应一个可独立验证的组件或交互。
>
> 技术栈已确定：Svelte 5 + Vite + D3 force + Lucide icons + Inter font
>
> 前端文件结构（待设计细化时可能调整）：
>
> ```
> web/
> ├── package.json, vite.config.ts, tsconfig.json, svelte.config.js, index.html
> ├── src/
> │   ├── main.ts
> │   ├── App.svelte
> │   ├── app.css
> │   ├── api/        (client.ts, sse.ts)
> │   ├── lib/        (types.ts, markdown.ts)
> │   ├── stores/     (graph.ts)
> │   ├── views/      (GraphView, ActivityView, ChatView)
> │   └── components/ (graph/, activity/, chat/, import/, flame/)
> ```

---

## Phase 4: Demo 打磨（后端 + 前端完成后）

### Task D1: 种子数据脚本

- [ ] 创建 `scripts/demo_seed.py` — 填充 17 个 AI/ML 实体、28 条关系、活动日志、复习数据
- [ ] 创建 `scripts/demo_verify.py` — 验证数据完整性
- [ ] 端到端验证

---

## API 总览（Phase 1 完成后）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/graph/full` | GET | 完整知识图谱 |
| `/api/graph/entity/{name}/card` | GET | 实体结构化笔记卡片 |
| `/api/graph/path` | GET | 两实体最短路径 |
| `/api/graph/gaps` | GET | 盲区建议列表 |
| `/api/graph/build` | POST | 重建图谱 |
| `/api/ingest/upload` | POST | Web 文件上传 |
| `/api/activity/heatmap` | GET | 热力图数据 |
| `/api/activity/day` | GET | 某日活跃详情 |
| `/api/activity/summary` | GET | 周摘要 |
| `/api/review/due` | GET | 待复习列表 |
| `/api/review/{entity_id}` | POST | 记录复习 |
| `/api/chat` | POST | SSE 对话（支持 socratic 模式） |
