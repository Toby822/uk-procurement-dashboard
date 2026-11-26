"""Plot the publication-date counts in the cached procurement sample."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    counts = Counter()
    for file in Path('data/tender_index').glob('*.json'):
        for notice in json.loads(file.read_text())['page']['releases']:
            day = datetime.fromisoformat(notice['date']).astimezone(timezone.utc).date()
            counts[day] += 1
    days = sorted(counts)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.edgecolor': '#c9d4dd', 'svg.fonttype': 'none',
                         'text.color': '#172e42', 'axes.labelcolor': '#172e42'})
    fig, ax = plt.subplots(figsize=(12, 4.4))
    fig.patch.set_facecolor('#f8fafc')
    ax.set_facecolor('#f8fafc')
    bars = ax.bar(range(len(days)), [counts[day] for day in days], color='#177f79', width=.65)
    ax.bar_label(bars, fontsize=9, padding=3)
    ax.set_xticks(range(len(days)), [day.strftime('%d %b') for day in days])
    ax.set(ylabel='Notice releases', xlabel='Publication date · UTC')
    ax.set_ylim(0, max(counts.values()) * 1.17)
    ax.grid(axis='y', color='#e2e8ed', linewidth=.7)
    ax.set_axisbelow(True)
    fig.suptitle('1,400 notices across 1,311 procurement processes', x=.07, ha='left', fontsize=16, fontweight='bold')
    fig.text(.07, .025, 'Find a Tender · first 14 pages of the bounded July 2025 update query', color='#526779')
    fig.subplots_adjust(left=.07, right=.98, top=.82, bottom=.2)
    fig.savefig('results/publications.svg', metadata={'Date': None})
    plt.close(fig)


if __name__ == '__main__':
    main()
