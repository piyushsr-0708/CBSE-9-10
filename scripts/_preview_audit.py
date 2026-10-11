import pandas as pd
df = pd.read_csv('reports/mapping_quality_audit.csv')

def show(q):
    print(f'\n--- SCORE: {q["confidence"]} | STAT: {q["classification_status"]} | {q["subject"]}_{q["class"]} ---')
    print(f'TEXT: {str(q["question_text"])[:200]}...')
    print(f'MAPPED CH: {q["chapter_id"]} | MAPPED TOPIC: {q["topic_id"]}')
    print(f'CONCERN: {q["reason_for_concern"]}')

print('--- HIGH SCORES (>0.45) ---')
for _, r in df[df["confidence"] > 0.45].head(5).iterrows(): show(r)

print('\n--- MID SCORES (0.25 - 0.45) ---')
for _, r in df[(df["confidence"] > 0.25) & (df["confidence"] <= 0.45)].head(5).iterrows(): show(r)

print('\n--- LOW SCORES (<0.25) ---')
for _, r in df[df["confidence"] <= 0.25].head(5).iterrows(): show(r)

print('\n--- OUT OF SYLLABUS ---')
for _, r in df[df["classification_status"] == "out_of_syllabus"].head(3).iterrows(): show(r)

print('\n--- UNCLASSIFIABLE ---')
for _, r in df[df["classification_status"] == "unclassifiable"].head(3).iterrows(): show(r)
