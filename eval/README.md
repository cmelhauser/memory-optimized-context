# Recall evaluation

The one instrument that makes "optimisation" mean something. Keep a frozen set of questions
whose answers you know are in the store, and measure recall@k before and after any change to
scoring, chunking, the prompt, or the embedding setting. If the number drops, revert.

`questions.jsonl` (git-ignored; it is about your store) has one object per line:

```json
{"query": "dbcache after IBD", "project": "bitcoin-node", "expect": ["1024"]}
```

`expect` is a list of substrings; the question counts as recalled if any active lesson in the
top k contains every substring. Start from `questions.example.jsonl` and grow it to about fifty.

```bash
tools/eval_recall.py eval/questions.jsonl            # native
docker exec memory python3 /app/eval_recall.py "$HOME/memory/eval/questions.jsonl"   # Docker
```
