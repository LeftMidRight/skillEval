import reTGT = "D:/Code/bytedanceCamp/evaluation/module3/downstream.py"with open(TGT, "r", encoding="utf-8") as f:    c = f.read()print("Read", len(c), "chars")
# Patch 1: fact/indicator dispatch -> use direct comparison
old1 = '    if task_type == "fact":
        return _compare_fact(llm_result, gt_rows)
    elif task_type == "indicator":
        return _compare_indicator(llm_result, gt_rows)
    else:
        return _compare_reasoning(llm_result, gt_rows, task_desc)'
new1 = '    if task_type == "fact":
        return _compare_fact_direct(las_markdown, gt_rows)
    elif task_type == "indicator":
        return _compare_indicator_direct(las_markdown, gt_rows)
    else:
        return _compare_reasoning(llm_result, gt_rows, task_desc)'
if old1 in c:
    c = c.replace(old1, new1)
    print("Patched dispatch")
else:
    print("Dispatch MISS")

# Patch 2: remove fact/indicator prompt branches
old2 = 'if task_type == "fact":
        system_prompt = FACT_PROMPT
    elif task_type == "indicator":
        system_prompt = INDICATOR_PROMPT
    else:
        system_prompt = REASONING_PROMPT'
new2 = 'if task_type == "reasoning":
        system_prompt = REASONING_PROMPT'
if old2 in c:
    c = c.replace(old2, new2)
    print("Patched prompts")
else:
    print("Prompts MISS")

with open(TGT, "w", encoding="utf-8") as f:
    f.write(c)
print("Written:", len(c), "chars")
