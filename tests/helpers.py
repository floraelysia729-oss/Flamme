"""测试辅助 — 写 markdown 文件"""


def write_md(path: str, title: str, content: str, level: str = "lite", tags: list | None = None):
    tags = tags or []
    tag_yaml = ", ".join(tags)
    text = (
        f"---\ntitle: {title}\nlevel: {level}\n"
        f"tags: [{tag_yaml}]\n---\n\n{content}"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
