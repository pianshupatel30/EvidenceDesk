# Learn EvidenceDesk by changing it

You can work through this guide one small session at a time. The sample documents describe a fictional arts centre; all names, policies, and questions are practice material.

## Session 1: use the app before studying the code

1. Open EvidenceDesk in your browser. Keep the server terminal open.
2. Type `How do I book a workshop?` and click **Find evidence**.
3. Read the matching source excerpt. Click the source reference to preview the document.
4. Type `What will the weather be tomorrow?`. Notice the insufficient-evidence message.
5. Search the document library for `workshops`. Open the document and read it.
6. Open **Activity**. Your requests appear with timings and outcomes.

In the free mode, the app selects document text. It does not generate a new answer with an LLM. With a provider configured, retrieval supplies the evidence for model-generated answers. You do not train a model in this project.

## Session 2: make your first content change

Open the project folder in VS Code with File > Open Folder. Open `documents/02_workshops.md` and read it. The file is ordinary text.

Create `practice.txt` in Notepad and paste this fictional example:

```text
The practice observatory opens at 8 pm on Fridays. Visitors must bring a red entry pass.
```

Save it, then use **Add documents** in the browser. Ask `What entry pass must observatory visitors bring?` and inspect the source. The app stores uploaded documents under `documents/user_*`. This is your first experiment with adding knowledge to a retrieval system.

## Session 3: follow one request through the code

Ask `How do I book a workshop?` and trace these files:

1. `evidencedesk/static/app.js` reads your question and sends JSON to `/api/ask`.
2. `evidencedesk/api.py` validates question length and the selected search method.
3. `evidencedesk/pipeline.py` coordinates retrieval, optional generation, and logging.
4. `evidencedesk/retrieval.py` scores and ranks document passages.
5. The relevance gate checks similarity and query-term coverage. Excerpt mode shows the top passage. With a model configured, `providers.py` sends the evidence to that model and validates its response.
6. `evidencedesk/telemetry.py` stores request measurements in SQLite.
7. The browser displays the answer, source references, and retrieved passages.

A function is a named set of instructions. A dictionary stores named values. JSON is the text format used here to exchange those values between Python and the browser. An API endpoint is a URL that accepts a request and returns data.

## Session 4: understand the measurements

| Term | Meaning here |
| --- | --- |
| Chunk | A passage of up to 180 words with a source filename and page number |
| BM25 | Keyword scoring that accounts for term frequency and document length |
| TF-IDF | A vocabulary-based vector representation used in free mode |
| Semantic embedding | An optional learned numerical representation for meaning-based similarity |
| Cosine similarity | A comparison between the query vector and a passage vector |
| Reciprocal rank fusion | Combines rankings by adding `1 / (60 + rank)` from each method |
| Reranking | Scores retrieved candidates again before selecting final passages |
| Abstention | The system reports that its evidence is insufficient |
| Hit@5 | Fraction of answerable questions whose expected source appears in the top five |
| MRR@5 | Average reciprocal rank of the first relevant result, with zero for a miss |
| Unsupported rejection | Fraction of unsupported questions rejected by the relevance gate |
| Answerable acceptance | Fraction of answerable questions accepted by that gate |
| P95 latency | A time at or below which approximately 95% of measured requests fall |

Hit@5 checks a source-document label. A relevant document may still lack the specific fact a question needs. Inspect source text as well as scores.

## Session 5: inspect real failures

Open **Evaluation**, click **Run benchmark**, and enable **Show review cases only**. The bundled report is also in `reports/demo_evaluation.json` and summarized in `reports/BASELINE.md`.

Inspect q055: `How many days does a workshop refund take to arrive?`. The cancellation document mentions refunds but gives no payment-processing duration. The relevance gate accepts that question because enough words overlap. Read `documents/04_cancellations.md` and identify the missing fact.

Now inspect q001: `What time does the arts centre open on weekends?`. The opening-hours document contains Saturday and Sunday hours, but the free lexical gate rejects this wording. Compare it with `What are the weekend opening hours?`, which the current gate accepts.

This demonstrates both kinds of error: accepting insufficient evidence and rejecting useful evidence. Keep both visible when evaluating improvements. The new corpus has its own measured baseline; changing content changes the results.

## Next experiments

1. Compare keyword and hybrid search for the same question. Record the passage order and latency.
2. Change one threshold in `.env`, restart, and save a report with `python -m evidencedesk.evaluate --output reports/experiment_01.json`.
3. Compare unsupported rejection and answerable acceptance. A threshold change can improve one while harming the other.
4. Create a separate development set for tuning and keep a later test set untouched.
5. Add longer documents, paraphrases, contradictory passages, and unsupported questions sharing vocabulary with the corpus.
6. If your computer supports it, enable semantic embeddings or a local model using README. Measure their effect rather than assuming improvement.

## Explain it in an interview

Demonstrate a successful retrieval, an abstention, and a known failure. Explain why the project combines two rankings, how sources are tracked, and why a valid citation alone does not prove that a claim is supported.

Describe the parts you can explain and the changes you personally made. For any result, state the dataset, search mode, and metric. The bundled synthetic dataset is small, so it cannot demonstrate performance on a large real-world corpus.

Practice answering these aloud:

- What happens after someone clicks Find evidence?
- Why split a document into overlapping chunks?
- How does the free vector search differ from semantic embeddings?
- Why can a relevant document still be insufficient?
- What happens when a model request fails?
- Which data does Activity store, and where?
- How would you evaluate a change before shipping it?

## Put your work on GitHub

Use a repository named `evidencedesk`. Include source files, README, LEARN, the synthetic sample documents, evaluation questions, reports, tests, and font licenses.

Keep `.env`, `.venv`, request databases, and personal uploaded documents out of GitHub. The bundled `.gitignore` covers these paths when using Git. Inspect the changed-files list before committing. A browser upload needs the same manual exclusions.

Add your own short demo and a paragraph describing what you learned or changed. A public repository makes the code viewable; a live hosted demo is a separate deployment step. The local address works only on the computer running the server.
