import re

html_path = 'frontend/index.html'
css_path = 'frontend/index.css'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

match = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
if match:
    style_content = match.group(1).strip()
    with open(css_path, 'r', encoding='utf-8') as f:
        css = f.read()
    
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(css + '\n\n' + style_content)
        
    new_html = html[:match.start()] + '<link rel="stylesheet" href="index.css">' + html[match.end():]
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
        print('Extracted successfully!')
