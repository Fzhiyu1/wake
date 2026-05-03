#!/bin/bash
# 把 knowledge-base 全量拼成 kb-snapshot.txt
# 每次知识库写入后跑一次,保持 wake substrate 与 KB 同步

set -e

KB="/Users/fangzhiyu/run/knowledge-base"
OUT="/Users/fangzhiyu/run/wake/kb-snapshot.txt"
TMP="${OUT}.tmp"

if [ ! -d "$KB" ]; then
    echo "knowledge-base not found at $KB" >&2
    exit 1
fi

> "$TMP"

# 先放导航索引(给 wake 地形感)
for idx in TERRAIN.md CLUSTERS.md INDEX.md GRAPH.md; do
    if [ -f "$KB/$idx" ]; then
        echo "=== $idx ===" >> "$TMP"
        cat "$KB/$idx" >> "$TMP"
        echo "" >> "$TMP"
    fi
done

# 按 PARA 顺序遍历所有卡(1-concepts → 2-explorations → 3-projects → 4-references → 0-inbox)
for dir in 1-concepts 2-explorations 3-projects 4-references 0-inbox; do
    if [ -d "$KB/$dir" ]; then
        find "$KB/$dir" -name "*.md" -type f | sort | while IFS= read -r f; do
            name=$(basename "$f" .md)
            echo "=== $name ===" >> "$TMP"
            cat "$f" >> "$TMP"
            echo "" >> "$TMP"
        done
    fi
done

mv "$TMP" "$OUT"

CARDS=$(grep -c "^=== " "$OUT")
SIZE=$(wc -c < "$OUT" | tr -d ' ')
echo "snapshot rebuilt: $CARDS sections, $SIZE bytes → $OUT"
