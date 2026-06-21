export const meta = {
  name: 'aqa-residual-discovery',
  description: 'Find official AQA spec PDFs for 8 residual codes (Dance, L2 Further Maths/Statistics, legacy D&T, Persian)',
  phases: [{ title: 'Discover', detail: 'one agent per residual AQA code' }],
}

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { results: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    properties: {
      code: { type: 'string' },
      actual_code: { type: 'string', description: 'the real AQA spec code if it differs from the queried one, else same' },
      title: { type: 'string' },
      pdf_url: { type: 'string' }, page_url: { type: 'string' },
      verified: { type: 'boolean' }, notes: { type: 'string' },
    },
    required: ['code','actual_code','title','pdf_url','page_url','verified','notes'],
  } } }, required: ['results'],
}

const CODES = [
  ['7562', 'AQA A-level Dance'],
  ['7202', 'AQA GCSE Statistics (a 72xx code — verify whether this is GCSE Statistics 8382, AS Statistics, or a Level 2/3 qualification)'],
  ['7203', 'AQA Level 2 Certificate Further Mathematics'],
  ['7204', 'AQA Level 2 Certificate Further Mathematics (legacy variant)'],
  ['7205', 'AQA Level 2 Certificate Further Mathematics (legacy variant)'],
  ['7206', 'AQA Level 2 Certificate Further Mathematics (legacy variant)'],
  ['8063', 'AQA GCSE Design and Technology: Fashion and Textiles (legacy, pre-2017)'],
  ['8688', 'AQA GCSE Persian'],
]

const RULES = `Find the OFFICIAL AQA specification (syllabus) PDF for the given code.
- AQA PDFs live at https://filestore.aqa.org.uk/resources/<slug>/specifications/AQA-<CODE>-SP-<YEAR>.PDF (or AQA-<CODE>-W-SP-<YY>.PDF for legacy). AS+A-level subjects often combine into AQA-<AScode>-<A2code>-SP-<YEAR>.PDF.
- Use WebSearch + WebFetch to find and CONFIRM the actual spec PDF (not a past paper / mark scheme / sample assessment).
- IMPORTANT: the queried code may be WRONG or may be the user's internal question-paper code. Determine the REAL AQA specification code for this qualification and put it in actual_code; give the PDF for that real spec.
- Legacy specs may only exist on web.archive.org or third-party mirrors — that is acceptable; return the best working PDF URL.
- verified=true only if you fetched the PDF and confirmed it is the spec. If the qualification genuinely never existed or no PDF is findable anywhere, set pdf_url="" page_url="" verified=false notes="NOT_OFFERED: <reason>".
- NEVER invent a URL. Return ONLY the structured object with exactly one result entry.`

phase('Discover')
const results = await parallel(CODES.map(([code, title]) => () =>
  agent(`${RULES}\n\nCODE: ${code}\nQUALIFICATION: ${title}`,
    { label: `aqa:${code}`, phase: 'Discover', schema: SCHEMA, agentType: 'Explore' })
    .then(r => (r && Array.isArray(r.results)) ? r.results : [])
    .catch(() => [])
))

const all = []
for (const arr of results) if (Array.isArray(arr)) all.push(...arr)
log(`residual discovery returned ${all.length} entries`)
return { results: all }
