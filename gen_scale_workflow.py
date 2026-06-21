#!/usr/bin/env python3
"""Generate wf_discover_scale.js with the 149 missing targets embedded as a
literal, one discovery agent per (board, subject) cell."""
import json, collections, os

ROOT = os.path.dirname(os.path.abspath(__file__))
missing = json.load(open(os.path.join(ROOT, "missing_all.json"), encoding="utf-8"))

cells = collections.OrderedDict()
for r in missing:
    cells.setdefault((r["board"], r["subject"]), []).append({
        "qual_type": r["qual_type"], "variant": r.get("variant", ""),
        "spec_code": r.get("spec_code", ""), "first_year": str(r["first_year"]),
        "last_year": str(r["last_year"]), "status": r["status"],
        "hint": r.get("notes", ""),
    })

CELLS = [{"board": b, "subject": s, "targets": t} for (b, s), t in cells.items()]

js = '''export const meta = {
  name: 'discover-scale-urls',
  description: 'Find + verify official spec PDF URLs for all missing versions across 23 subjects (one agent per board-subject cell)',
  phases: [{ title: 'Discover', detail: 'one web-research agent per (board, subject) cell' }],
}

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { targets: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    properties: {
      board: { type: 'string' }, qual_type: { type: 'string' }, variant: { type: 'string' },
      subject: { type: 'string' }, spec_code: { type: 'string' },
      first_year: { type: 'string' }, last_year: { type: 'string' }, status: { type: 'string' },
      pdf_url: { type: 'string' }, page_url: { type: 'string' },
      verified: { type: 'boolean' }, notes: { type: 'string' },
    },
    required: ['board','qual_type','variant','subject','spec_code','first_year','last_year','status','pdf_url','page_url','verified','notes'],
  } } }, required: ['targets'],
}

const CELLS = ''' + json.dumps(CELLS, ensure_ascii=False) + ''';

const RULES = `You locate OFFICIAL exam-board specification (syllabus) PDFs and verify them.
- Return ONE entry per target listed, copying board/qual_type/variant/subject/spec_code/first_year/last_year/status EXACTLY.
- Use WebSearch then WebFetch to CONFIRM the URL is the real specification PDF (NOT a sample assessment, mark scheme, question paper, examiner report, or HTML page).
- pdf_url = direct https link ending .pdf on the OFFICIAL domain. page_url = official spec landing page linking the PDF.
- verified=true ONLY if you fetched the pdf_url and confirmed it is the spec PDF; else verified=false but give best pdf_url/page_url.
- If a version genuinely is not offered / cannot be found, set pdf_url="" page_url="" verified=false notes="NOT_OFFERED: <reason>".
- NEVER invent a URL. Empty string beats a guess. Return ONLY the structured object.`

const DOMAIN = {
  AQA: 'AQA PDFs: https://filestore.aqa.org.uk/resources/<slug>/specifications/AQA-<CODE>-SP-<YEAR>.PDF (slugs e.g. biology, mathematics, english, history, geography, psychology, sociology, economics, business, computing, rs, spanish, french, politics, pe, music, drama, design-and-technology, media-studies, art-and-design, science). Pre-2017 LEGACY specs are usually NOT on the filestore -> check the AQA subject page past-specifications and web.archive.org.',
  Edexcel: 'Edexcel/Pearson PDFs under https://qualifications.pearson.com/content/dam/pdf/... Find the spec landing page on qualifications.pearson.com and the linked specification PDF. IGCSE/IAL/iPrimary/iLowerSecondary live in their own sections. Legacy specs may need web.archive.org.',
  OCR: 'OCR PDFs: https://www.ocr.org.uk/Images/<id>-specification-...pdf . Find the subject page on ocr.org.uk. Cambridge Nationals are under ocr.org.uk/qualifications/cambridge-nationals/. Legacy unit specs may need web.archive.org.',
  IB: 'IB guide PDFs at https://www.ibo.org/globalassets/... (may 403 -> still return the URL), store.ibo.org, or archived copies on school sites / web.archive.org. DP guides have first-assessment generations (2009/2014/2016/2019/2021/2023/2025). Return the subject guide PDF for the stated first_year.',
}

phase('Discover')
const results = await parallel(CELLS.map((cell) => () => {
  const board = cell.board
  const lines = cell.targets.map(t =>
    `- ${board} ${t.qual_type} ${t.variant} ${cell.subject} code=${t.spec_code} ${t.first_year}->${t.last_year} ${t.status}${t.hint ? '  ['+t.hint.slice(0,80)+']' : ''}`).join('\\n')
  const prompt = `${RULES}\\n\\nBOARD CONTEXT: ${DOMAIN[board] || ''}\\n\\nFIND THESE ${cell.targets.length} ${board} ${cell.subject} specification versions:\\n${lines}`
  return agent(prompt, { label: `disc:${board}:${cell.subject}`, phase: 'Discover', schema: SCHEMA, agentType: 'Explore' })
    .then(r => (r && Array.isArray(r.targets)) ? r.targets : [])
    .catch(() => [])
}))

const all = []
for (const arr of results) if (Array.isArray(arr)) all.push(...arr)
log(`discovered ${all.length} candidate targets across ${CELLS.length} cells`)
return { targets: all }
'''

out = os.path.join(ROOT, "wf_discover_scale.js")
open(out, "w", encoding="utf-8").write(js)
print(f"wrote {out} with {len(CELLS)} cells / {len(missing)} targets")
