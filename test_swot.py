#!/usr/bin/env python3

import sys
sys.path.append('.')

from app import generate_swot_analysis, analyze_overall_question_selection

# Test data structure similar to what would come from a full mock test
test_stats = {
    'test_id': 1,  # Full mock test ID
    'answer_data': {
        '0': {  # VARC section
            '0': {'answer': 'A'},
            '1': {'answer': 'B'},
            '2': {'answer': None},  # Skipped
            '3': {'answer': 'C'},
            '4': {'answer': 'D'},
        },
        '1': {  # LRDI section
            '0': {'answer': 'A'},
            '1': {'answer': None},  # Skipped
            '2': {'answer': 'B'},
            '3': {'answer': 'C'},
        },
        '2': {  # QA section
            '0': {'answer': 'A'},
            '1': {'answer': 'B'},
            '2': {'answer': None},  # Skipped
            '3': {'answer': 'C'},
            '4': {'answer': 'D'},
        }
    },
    'question_times': {
        '0': {  # VARC section times
            '0': 45,
            '1': 60,
            '2': 0,  # Skipped
            '3': 90,
            '4': 75,
        },
        '1': {  # LRDI section times
            '0': 120,
            '1': 0,  # Skipped
            '2': 85,
            '3': 110,
        },
        '2': {  # QA section times
            '0': 80,
            '1': 95,
            '2': 0,  # Skipped
            '3': 120,
            '4': 60,
        }
    },
    'sections': [
        {'name': 'Verbal Ability and Reading Comprehension', 'score': 9, 'correct': 3, 'wrong': 1, 'skipped': 1},
        {'name': 'Data Interpretation & Logical Reasoning', 'score': 6, 'correct': 2, 'wrong': 0, 'skipped': 2},
        {'name': 'Quantitative Aptitude', 'score': 9, 'correct': 3, 'wrong': 0, 'skipped': 2}
    ]
}

print("Testing SWOT Analysis with Mock Data...")
print("=" * 50)

# Test the SWOT analysis
result = generate_swot_analysis(test_stats)

print("SWOT Analysis Result:")
print("=" * 30)

for category, items in result.items():
    print(f"\n{category.upper()}:")
    for item in items:
        print(f"  • {item['title']}")
        print(f"    {item['description']}")
        print(f"    Tags: {item['tags']}")

# Also test the overall metrics function directly
print("\n" + "=" * 50)
print("Testing Overall Metrics Function...")

sections_conf = [
    { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'Complete_VARC_Question_Set.csv', 'short_name': 'VARC' },
    { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'DILR_Question_Set.csv', 'short_name': 'LRDI' },
    { 'name': "Quantitative Aptitude", 'csv': 'QA_Question_Set.csv', 'short_name': 'QA' }
]

try:
    overall_metrics = analyze_overall_question_selection(sections_conf, test_stats['answer_data'], test_stats['question_times'])
    print("Overall Metrics:")
    for key, value in overall_metrics.items():
        print(f"  {key}: {value}")
except Exception as e:
    print(f"Error in overall metrics: {e}") 