import json
import glob
import os
import html

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clinical Trial Extractions</title>
    <style>
        * {
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 0;
            background: #f8f9fa;
            color: #212529;
            line-height: 1.5;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }

        header {
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #dee2e6;
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0 0 1rem 0;
        }

        .study-selector {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .study-selector label {
            font-size: 0.875rem;
            color: #495057;
        }

        .study-selector select {
            flex: 1;
            max-width: 400px;
            padding: 0.5rem;
            font-size: 0.875rem;
            border: 1px solid #ced4da;
            background: #fff;
            cursor: pointer;
        }

        .study-selector select:focus {
            outline: none;
            border-color: #495057;
        }

        .study-content {
            display: none;
        }

        .study-content.active {
            display: block;
        }

        .fields-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 1rem;
        }

        .field {
            background: #fff;
            border: 1px solid #dee2e6;
            display: flex;
            flex-direction: column;
        }

        .field-header {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #dee2e6;
            font-weight: 600;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.025em;
        }

        .field-content {
            padding: 1rem;
            max-height: 300px;
            overflow-y: auto;
        }

        .field-content.empty {
            color: #868e96;
            font-style: italic;
            font-size: 0.875rem;
        }

        .extraction {
            padding: 0.625rem 0.75rem;
            margin-bottom: 0.5rem;
            font-size: 0.875rem;
            border-left: 3px solid currentColor;
        }

        /* Field-specific colors */
        .field-arms .field-header { background: #e7f1f8; color: #1a5a8a; }
        .field-arms .extraction { background: #f4f9fc; color: #1a5a8a; }

        .field-enrollment .field-header { background: #e8eaf6; color: #3949ab; }
        .field-enrollment .extraction { background: #f5f6fb; color: #3949ab; }

        .field-endpoints .field-header { background: #e8f5e9; color: #2e6b33; }
        .field-endpoints .extraction { background: #f5fbf5; color: #2e6b33; }

        .field-response .field-header { background: #fff8e6; color: #8a6d1a; }
        .field-response .extraction { background: #fffcf4; color: #8a6d1a; }

        .field-adverse_events .field-header { background: #fce8e8; color: #8a3a3a; }
        .field-adverse_events .extraction { background: #fef5f5; color: #8a3a3a; }

        .field-inclusion_criteria .field-header { background: #e8f4f0; color: #2a6b5a; }
        .field-inclusion_criteria .extraction { background: #f4faf8; color: #2a6b5a; }

        .field-exclusion_criteria .field-header { background: #f3e8f4; color: #6b2a6b; }
        .field-exclusion_criteria .extraction { background: #faf4fa; color: #6b2a6b; }

        .extraction:last-child {
            margin-bottom: 0;
        }

        .count {
            font-size: 0.75rem;
            color: #868e96;
            font-weight: normal;
            margin-left: 0.5rem;
        }

        .study-header {
            background: #fff;
            border: 1px solid #dee2e6;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }

        .study-header h2 {
            margin: 0 0 0.5rem 0;
            font-size: 1.1rem;
            font-weight: 600;
            color: #212529;
        }

        .study-meta {
            font-size: 0.875rem;
            color: #495057;
        }

        .study-meta span {
            display: inline-block;
            margin-right: 1.5rem;
        }

        .study-meta .label {
            color: #868e96;
        }

        .trial-ids {
            margin-top: 0.5rem;
            font-size: 0.8rem;
        }

        .trial-ids a {
            color: #1a5a8a;
            text-decoration: none;
            margin-right: 0.75rem;
        }

        .trial-ids a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Clinical Trial Extractions</h1>
            <div class="study-selector">
                <label for="study-select">Study:</label>
                <select id="study-select" onchange="showStudy(this.value)">
                    {{OPTIONS}}
                </select>
            </div>
        </header>
        <main>
            {{STUDIES}}
        </main>
    </div>
    <script>
        function showStudy(id) {
            document.querySelectorAll('.study-content').forEach(el => {
                el.classList.remove('active');
            });
            document.getElementById(id).classList.add('active');
        }
    </script>
</body>
</html>
'''

FIELD_LABELS = {
    'arms': 'Study Arms',
    'enrollment': 'Enrollment',
    'response': 'Response',
    'endpoints': 'Endpoints',
    'adverse_events': 'Adverse Events',
    'inclusion_criteria': 'Inclusion Criteria',
    'exclusion_criteria': 'Exclusion Criteria'
}


def generate_field_html(field_name, items):
    label = FIELD_LABELS.get(field_name, field_name)
    count = len(items) if items else 0

    if not items:
        content = '<div class="field-content empty">No extractions found</div>'
    else:
        extractions = '\n'.join(
            f'<div class="extraction">{html.escape(item)}</div>'
            for item in items
        )
        content = f'<div class="field-content">{extractions}</div>'

    return f'''<div class="field field-{field_name}">
    <div class="field-header">{label}<span class="count">({count})</span></div>
    {content}
</div>'''


def parse_study_info(study_info_str):
    """Parse the study_info string into a dict."""
    info = {}
    if not study_info_str:
        return info
    for part in study_info_str.split('|'):
        part = part.strip()
        if ':' in part:
            key, value = part.split(':', 1)
            info[key.strip().lower()] = value.strip()
    return info


def generate_study_header(data):
    """Generate the study header HTML."""
    study_info = parse_study_info(data.get('study_info', ''))
    trial_ids = data.get('trial_ids', [])

    title = html.escape(study_info.get('title', 'Unknown Title'))
    trial_name = study_info.get('trial', '')
    year = study_info.get('year', '')
    journal = study_info.get('journal', '')

    meta_parts = []
    if trial_name:
        meta_parts.append(f'<span><span class="label">Trial:</span> {html.escape(trial_name)}</span>')
    if year:
        meta_parts.append(f'<span><span class="label">Year:</span> {html.escape(year)}</span>')
    if journal:
        meta_parts.append(f'<span><span class="label">Journal:</span> {html.escape(journal)}</span>')
    meta_html = ''.join(meta_parts)

    trial_ids_html = ''
    if trial_ids:
        links = []
        for tid in trial_ids:
            if tid.startswith('NCT'):
                url = f'https://clinicaltrials.gov/study/{tid}'
                links.append(f'<a href="{url}" target="_blank">{tid}</a>')
            else:
                links.append(html.escape(tid))
        trial_ids_html = f'<div class="trial-ids"><span class="label">Registry:</span> {" ".join(links)}</div>'

    return f'''<div class="study-header">
    <h2>{title}</h2>
    <div class="study-meta">{meta_html}</div>
    {trial_ids_html}
</div>'''


def generate_study_html(study_id, data, is_first):
    active_class = ' active' if is_first else ''
    header_html = generate_study_header(data)
    fields_html = '\n'.join(
        generate_field_html(field, data.get(field, []))
        for field in ['arms', 'enrollment', 'inclusion_criteria', 'exclusion_criteria', 'endpoints', 'response', 'adverse_events']
    )
    return f'<div id="{study_id}" class="study-content{active_class}">\n{header_html}\n<div class="fields-grid">\n{fields_html}\n</div>\n</div>'


def main():
    json_files = sorted(glob.glob('*.json'))

    if not json_files:
        print('No JSON files found')
        return

    studies = []
    for fname in json_files:
        with open(fname) as f:
            try:
                data = json.load(f)
                study_name = os.path.splitext(fname)[0]
                studies.append((study_name, data))
            except json.JSONDecodeError:
                print(f'Skipping invalid JSON: {fname}')

    if not studies:
        print('No valid studies found')
        return

    options = '\n'.join(
        f'<option value="{name}">{name.replace("_", " ")}</option>'
        for name, _ in studies
    )

    studies_html = '\n'.join(
        generate_study_html(name, data, i == 0)
        for i, (name, data) in enumerate(studies)
    )

    html_output = HTML_TEMPLATE.replace('{{OPTIONS}}', options).replace('{{STUDIES}}', studies_html)

    with open('extractions.html', 'w') as f:
        f.write(html_output)

    print(f'Generated extractions.html with {len(studies)} studies')


if __name__ == '__main__':
    main()
