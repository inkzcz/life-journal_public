"""Package controlled CHANGELOG text into the API image; run before committing release notes."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate(text):
    out=[];current=None
    for line in text.splitlines():
        match=re.match(r'^#{1,2}\s+(v?\d+\.\d+\.\d+[^\n]*)$',line)
        if match:
            if len(out)>=12:break
            current={'title':match[1],'body':''};out.append(current)
        elif current:current['body']+=(line+'\n')
    return [{'title':r['title'][:200],'body':r['body'].strip()[:6000]} for r in out]
if __name__=='__main__':
    (ROOT/'backend/app/release_notes.json').write_text(json.dumps(generate((ROOT/'CHANGELOG.md').read_text(encoding='utf-8')),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
