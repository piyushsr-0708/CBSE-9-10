with open("scripts/build_syllabus.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace('docs = [d for d in sources.get("documents", []) if d.get("download_status") == "success"]', 
                    'docs = [d for d in sources.get("documents", []) if d.get("download_status") == "success" and d["class"] == "9" and d["subject_csv"] in ["maths", "social_science"]]')

with open("scripts/build_syllabus.py", "w", encoding="utf-8") as f:
    f.write(text)
print("Updated to only run matched subjects.")
