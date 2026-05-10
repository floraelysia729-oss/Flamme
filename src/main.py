"""CLI 入口 — argparse 定义子命令: ingest / query / status / index / search

TS 映射: commander.js 或 yargs
"""

import argparse
import sys
import io

# Windows 终端 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from src.config import load_config
from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.embedding_store import EmbeddingStore
from src.tools.bootstrap import build_registry
from src.agent.agent import Agent
from src.agent.coordinator import Coordinator
from src.llm.queue import LLMQueue


def _build_agent(config) -> tuple[Agent, SQLiteClient]:
    """构建 Agent 实例（含 embedding store）"""
    db = SQLiteClient(config.db_path, vault_path=config.vault_path)

    # Embedding store
    embedding_store = EmbeddingStore(config.embeddings_dir, dim=config.embed_dim)

    # 如果有 API key 则初始化 LLM（chat 和 embed 可分开配置）
    llm = None
    if config.llm_api_key or config.embed_api_key:
        from src.llm.provider import DefaultLLM
        llm = DefaultLLM(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
            embed_api_key=config.embed_api_key,
            embed_base_url=config.embed_base_url,
            embed_model=config.embed_model,
        )

    # 共享工具注册
    registry = build_registry(config, db, llm=llm, embedding_store=embedding_store)

    queue = LLMQueue(max_concurrency=config.max_concurrency) if llm else None
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=embedding_store, llm_queue=queue)
    return agent, db


def _build_coordinator(agent: Agent, db: SQLiteClient, config,
                       max_workers: int = 3) -> Coordinator:
    """构建 Coordinator 实例（brain 用 GLM，worker 用 chat LLM）"""
    registry = agent._tools
    llm = agent._llm
    embedding_store = agent._embedding_store
    llm_queue = agent._llm_queue

    # Brain LLM — GLM 专用于多 Agent 编排决策
    brain_llm = None
    if config.brain_api_key:
        from src.llm.provider import DefaultLLM
        brain_llm = DefaultLLM(
            api_key=config.brain_api_key,
            base_url=config.brain_base_url,
            model=config.brain_model,
            embed_api_key=config.embed_api_key,
            embed_base_url=config.embed_base_url,
            embed_model=config.embed_model,
        )

    return Coordinator(
        agent=agent,
        db=db,
        tools=registry,
        llm=llm,
        brain_llm=brain_llm,
        embedding_store=embedding_store,
        llm_queue=llm_queue,
        max_workers=max_workers,
    )


def main():
    parser = argparse.ArgumentParser(
        prog="llm-wiki",
        description="LLM-WIKI 2.0 — 本地知识库助手",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # --- ingest ---
    ingest_parser = subparsers.add_parser("ingest", help="导入文件到知识库")
    ingest_parser.add_argument("path", help="文件路径")
    ingest_parser.add_argument("--level", choices=["raw", "lite", "pro"], default="lite", help="处理级别")
    ingest_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- query ---
    query_parser = subparsers.add_parser("query", help="查询知识库")
    query_parser.add_argument("question", help="问题")
    query_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- status ---
    status_parser = subparsers.add_parser("status", help="查看知识库统计")
    status_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- scan ---
    scan_parser = subparsers.add_parser("scan", help="扫描 vault 并导入所有 .md 文件")
    scan_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- index ---
    index_parser = subparsers.add_parser("index", help="为文档生成向量索引")
    index_parser.add_argument("--full", action="store_true", help="全量索引（含已索引文档）")
    index_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- search ---
    search_parser = subparsers.add_parser("search", help="语义搜索文档")
    search_parser.add_argument("query", help="搜索查询")
    search_parser.add_argument("--top", type=int, default=5, help="返回结果数 (默认 5)")
    search_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- graph ---
    graph_parser = subparsers.add_parser("graph", help="知识图谱操作")
    graph_sub = graph_parser.add_subparsers(dest="graph_action", help="图谱子命令")
    graph_build = graph_sub.add_parser("build", help="构建/更新知识图谱")
    graph_build.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")
    graph_query = graph_sub.add_parser("query", help="查询图谱节点邻居")
    graph_query.add_argument("node", help="节点名称")
    graph_query.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")
    graph_isolates = graph_sub.add_parser("isolates", help="查找孤立节点")
    graph_isolates.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")
    graph_community = graph_sub.add_parser("community", help="查看社区信息")
    graph_community.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- task (multi-agent) ---
    task_parser = subparsers.add_parser("task", help="多 Agent 任务编排")
    task_parser.add_argument("prompt", help="任务描述")
    task_parser.add_argument("--workers", type=int, default=3, help="Worker 数量 (默认 3)")
    task_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- sync ---
    sync_parser = subparsers.add_parser("sync", help="同步 vault 文件到 SQLite 索引")
    sync_parser.add_argument("--embed", action="store_true", help="同时生成向量索引")
    sync_parser.add_argument("--graph", action="store_true", help="同时重建知识图谱")
    sync_parser.add_argument("--vault", help="Vault 路径 (覆盖自动检测)")

    # --- 全局 --workers 参数 ---
    parser.add_argument("--workers", type=int, default=1, help="Worker 并发数 (默认 1=单 Agent)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 加载配置
    overrides = {}
    if hasattr(args, "vault") and args.vault:
        overrides["vault_path"] = args.vault
    config = load_config(**overrides)

    # 构建 agent
    agent, db = _build_agent(config)

    # 决定是否启用多 Agent 模式
    global_workers = getattr(args, "workers", 1)
    use_coordinator = global_workers > 1 or args.command == "task"
    coordinator = None

    if use_coordinator:
        task_workers = getattr(args, "workers", 3) if args.command != "task" else args.workers
        coordinator = _build_coordinator(agent, db, config, max_workers=task_workers)

    try:
        if args.command == "status":
            print(agent.run("status"))

        elif args.command == "scan":
            print(agent.run("scan"))

        elif args.command == "ingest":
            if coordinator:
                print(coordinator.run(f'ingest "{args.path}"', level=args.level))
            else:
                result = agent.run(f'ingest "{args.path}"', level=args.level)
                print(result)

        elif args.command == "query":
            if coordinator:
                print(coordinator.run(args.question))
            else:
                result = agent.run(args.question)
                print(result)

        elif args.command == "index":
            full_flag = "--full" if args.full else ""
            prompt = f"index {full_flag}".strip()
            if coordinator:
                print(coordinator.run(prompt))
            else:
                print(agent.run(prompt))

        elif args.command == "search":
            if coordinator:
                print(coordinator.run(f'search "{args.query}"', top_k=args.top))
            else:
                result = agent.run(f'search "{args.query}"', top_k=args.top)
                print(result)

        elif args.command == "graph":
            if not args.graph_action:
                print("用法: llm-wiki graph {build|query|isolates|community}")
                sys.exit(1)
            if args.graph_action == "build":
                print(agent.run("graph build"))
            elif args.graph_action == "query":
                print(agent.run(f'graph query "{args.node}"'))
            elif args.graph_action == "isolates":
                print(agent.run("graph isolated"))
            elif args.graph_action == "community":
                print(agent.run("graph community"))

        elif args.command == "task":
            print(coordinator.run(args.prompt))

        elif args.command == "sync":
            from src.tools.sync import SyncTool
            sync = SyncTool(db, config.vault_path)
            result = sync.execute({})
            if result.is_error:
                print(f"Sync failed: {result.error}")
                sys.exit(1)
            d = result.data
            print(f"Sync complete:")
            print(f"  Added: {len(d['added'])}")
            print(f"  Updated: {len(d['updated'])}")
            print(f"  Removed: {len(d['removed'])}")
            print(f"  Unchanged: {d['unchanged']}")
            print(f"  To embed: {len(d['to_embed'])}")
            print(f"  Total on disk: {d['total_disk']}, Total in DB: {d['total_db']}")
            # 可选：同步后生成向量
            if args.embed and d["to_embed"]:
                print("\nEmbedding new documents...")
                print(agent.run("index"))
            # 可选：重建图谱
            if args.graph:
                print("\nRebuilding graph...")
                print(agent.run("graph build"))

    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
