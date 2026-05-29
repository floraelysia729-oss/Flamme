-- LLM-WIKI 2.0 SQLite Schema

-- 文档元数据
CREATE TABLE IF NOT EXISTS documents (
  path TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  level TEXT CHECK(level IN ('raw','lite','pro','source')),
  status TEXT DEFAULT 'draft',
  content_hash TEXT,
  word_count INTEGER,
  embedding_id INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (embedding_id) REFERENCES embeddings(id)
);

-- 标签
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS document_tags (
  doc_path TEXT,
  tag_id INTEGER,
  PRIMARY KEY (doc_path, tag_id),
  FOREIGN KEY (doc_path) REFERENCES documents(path) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id)
);

-- 向量索引元数据
CREATE TABLE IF NOT EXISTS embeddings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_path TEXT UNIQUE,
  content_hash TEXT,
  dim INTEGER DEFAULT 1024,
  model TEXT DEFAULT 'text-embedding-v3',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (doc_path) REFERENCES documents(path) ON DELETE CASCADE
);

-- 实体与关系
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  type TEXT,
  wiki_path TEXT,
  community INTEGER DEFAULT -1,
  tags TEXT DEFAULT '',
  entity_file TEXT DEFAULT '',
  source_file TEXT DEFAULT '',
  level TEXT DEFAULT '',
  content_hash TEXT DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_entity INTEGER,
  target_entity INTEGER,
  relation_type TEXT,
  confidence REAL DEFAULT 1.0,
  source_doc TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_entity) REFERENCES entities(id),
  FOREIGN KEY (target_entity) REFERENCES entities(id)
);

-- 任务队列 (Phase 4)
CREATE TABLE IF NOT EXISTS task_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  payload TEXT,
  claimed_by TEXT,
  generation INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 时间维度
CREATE TABLE IF NOT EXISTS temporal_annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_path TEXT,
  entity_id INTEGER,
  observed_at DATE,
  superseded_by TEXT,
  note TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (doc_path) REFERENCES documents(path) ON DELETE CASCADE,
  FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- 对话历史（会话记忆）
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
  content TEXT,
  tool_calls TEXT,
  tool_call_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, created_at);

-- 检查点（断点续传）
CREATE TABLE IF NOT EXISTS checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operation TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT DEFAULT 'in_progress',
  snapshot TEXT,
  git_commit TEXT,
  started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 术语表（跨领域消歧）
CREATE TABLE IF NOT EXISTS glossary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  term TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  definition TEXT NOT NULL DEFAULT '',
  aliases TEXT DEFAULT '',
  seealso TEXT DEFAULT '',
  source TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(term, domain)
);

-- 增量迁移：已有 DB 补充 entities 新列（幂等，IF NOT EXISTS 通过 pragma 防重）
-- SQLite 不支持 IF NOT EXISTS for ALTER TABLE，用 pragma 检测列是否存在
CREATE TABLE IF NOT EXISTS _schema_migrations (
  migration TEXT PRIMARY KEY
);
