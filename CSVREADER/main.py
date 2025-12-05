"""
CSV LEFT → RIGHT replacer with Language selection + model-friendly flow
- CSV: LEFT = search (e.g. "Baseball"), RIGHT = replacement (e.g. "ಕ್ರಿಕೆಟ್")
- If lang == "kannada" and Use Groq == True:
    - FIRST apply LEFT->RIGHT to the user input (so model sees Kannada tokens)
    - THEN call the model with the modified prompt
    - Return model output (and which CSV replacements were applied to input)
- If Use Groq == False:
    - Apply LEFT->RIGHT to user input and return it (no model call)
"""

from flask import Flask, request, jsonify, render_template_string
import os, re, csv, unicodedata, requests, json

# ---------- CONFIG ----------
API_KEY = ""
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CSV_NAME = "Uploaded_CSV_preview.csv"
PORT = 8000
MODELS_TO_TRY = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama3-8b-8192"]
# ----------------------------

app = Flask(__name__)

# ---------- UTIL ----------
def norm(s):
    if s is None: return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\u200c","").replace("\u200d","").replace("\ufeff","")
    return re.sub(r"\s+"," ", s).strip()

# ---------- CSV LOADER ----------
def load_csv_pairs():
    path = os.path.join(os.path.dirname(__file__), CSV_NAME)
    pairs = []
    if not os.path.exists(path):
        print("[CSV NOT FOUND]", path)
        return pairs
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                left = norm(row[0])   # LEFT = search token (english)
                right = norm(row[1])  # RIGHT = replacement (kannada)
                if left and right:
                    pairs.append((left, right))
    print(f"[CSV] Loaded {len(pairs)} rows")
    return pairs

# ---------- PRESERVE CASE (simple Latin) ----------
def _preserve_case(original: str, replacement: str) -> str:
    if not original: return replacement
    try:
        if all(ord(c) < 128 for c in original):
            if original.isupper(): return replacement.upper()
            if original[0].isupper() and original[1:].islower(): return replacement.capitalize()
    except Exception:
        pass
    return replacement

# ---------- WHOLE WORD PATTERN ----------
def whole_word_pattern(tok):
    if not tok: return None
    tok = tok.strip()
    if tok == "": return None
    parts = tok.split()
    escaped = [re.escape(p) for p in parts]
    sep = r"(?:[\s\u00A0\-.,\u2013\u2014]+)"
    return r"(?<![\w\u0C80-\u0CFF])" + sep.join(escaped) + r"(?![\w\u0C80-\u0CFF])"

# ---------- APPLY LEFT->RIGHT REPLACEMENTS ----------
def apply_left_to_right(text: str, pairs):
    """
    pairs: list of (left_search, right_replace)
    Returns: final_text, applied_list
    applied_list items: {"search":..., "replace":..., "mode": "whole_word"/"substring", "count":int}
    """
    final = text
    applied = []
    if not pairs:
        return final, applied

    # sort by length of LEFT (search) to prefer longest matches first
    pairs_sorted = sorted(pairs, key=lambda t: len(t[0]), reverse=True)

    # WHOLE-WORD pass
    for search, replacement in pairs_sorted:
        pat = whole_word_pattern(search)
        if pat and re.search(pat, final, flags=re.IGNORECASE|re.UNICODE):
            def _r(m):
                return _preserve_case(m.group(0), replacement)
            final, cnt = re.subn(pat, _r, final, flags=re.IGNORECASE|re.UNICODE)
            applied.append({"search": search, "replace": replacement, "mode": "whole_word", "count": int(cnt)})

    # SUBSTRING fallback (literal)
    for search, replacement in pairs_sorted:
        esc = re.escape(search)
        if re.search(esc, final, flags=re.IGNORECASE|re.UNICODE):
            def _rsub(m):
                return _preserve_case(m.group(0), replacement)
            final, cnt = re.subn(esc, _rsub, final, flags=re.IGNORECASE|re.UNICODE)
            applied.append({"search": search, "replace": replacement, "mode": "substring", "count": int(cnt)})

    return final, applied

# ---------- GROQ HELPERS ----------
def extract_text(resp_json):
    try:
        ch = resp_json["choices"][0]
        if "message" in ch:
            return ch["message"]["content"]
        if "text" in ch:
            return ch["text"]
    except Exception:
        pass
    return json.dumps(resp_json)

def ask_groq(text, lang, api_key):
    sys_msg = "Respond concisely in Kannada." if lang=="kannada" else "Respond concisely in English."
    headers = {"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}
    for model in MODELS_TO_TRY:
        body = {"model": model, "messages":[{"role":"system","content":sys_msg},{"role":"user","content":text}], "max_tokens":500}
        try:
            r = requests.post(GROQ_URL, headers=headers, json=body, timeout=40)
        except Exception as e:
            return None, {"error":"network","detail":str(e)}
        if r.status_code == 200:
            return extract_text(r.json()), {"status":200, "model": model}
        if r.status_code in (401,403):
            return None, {"error":"auth","detail": r.text}
    return None, {"error":"no_model"}

# ---------- UI ----------
@app.route("/")
def ui():
    return render_template_string("""
<!doctype html>
<html>
<head><script src="https://cdn.tailwindcss.com"></script><title>CSV LEFT→RIGHT Replacer (model-friendly)</title></head>
<body class="bg-slate-50 p-6">
  <div class="max-w-3xl mx-auto bg-white p-6 rounded-xl shadow">
    <h1 class="text-2xl font-bold mb-2">CSV LEFT→RIGHT Replacer</h1>
    <p class="text-sm text-slate-500 mb-3">CSV: <b>{{csv}}</b> (LEFT = search -> RIGHT = replacement)</p>

    <label class="block mb-2 font-semibold">Language:</label>
    <select id="lang" class="border p-2 rounded mb-3"><option value="kannada">Kannada</option><option value="english">English</option></select>

    <label><input id="useModel" type="checkbox"> Use Groq model?</label>
    <input id="apiKey" class="border p-2 rounded w-full my-3" placeholder="Groq API key (optional)">
    <textarea id="text" rows="4" class="border p-3 rounded w-full mb-3" placeholder="Enter text… (e.g. I invite you to Baseball)"></textarea>

    <button id="runBtn" class="px-4 py-2 bg-blue-600 text-white rounded">Run</button>
    <div id="result" class="mt-6"></div>
  </div>

<script>
function esc(s){return (s||"").toString().replace(/&/g,'&amp;').replace(/</g,'&lt;');}
document.getElementById("runBtn").onclick = async () => {
  const body = { lang: document.getElementById("lang").value, use_model: document.getElementById("useModel").checked, text: document.getElementById("text").value, api_key: document.getElementById("apiKey").value };
  if(!body.text){ alert("Type text first!"); return; }
  const btn = document.getElementById("runBtn"); btn.disabled=true; btn.textContent="Running...";
  try {
    const r = await fetch("/process", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
    const data = await r.json();
    document.getElementById("result").innerHTML = "<pre class='bg-slate-100 p-4 rounded'>" + esc(JSON.stringify(data,null,2)) + "</pre>";
  } catch(err){
    document.getElementById("result").innerHTML = "<div class='bg-red-100 p-3 rounded text-red-700'>"+esc(err.message)+"</div>";
  }
  btn.disabled=false; btn.textContent="Run";
};
</script>
</body></html>
""", csv=CSV_NAME)

# ---------- PROCESS endpoint (important logic change here) ----------
@app.route("/process", methods=["POST"])
def process_endpoint():
    data = request.get_json(force=True) or {}
    lang = data.get("lang", "english")
    use_model = bool(data.get("use_model"))
    user_text = data.get("text", "")
    api_key = data.get("api_key") or API_KEY

    # load CSV pairs once
    pairs = load_csv_pairs()

    # If lang == kannada, we want to replace LEFT->RIGHT in the user input BEFORE calling model
    replacements_input = []
    prompt_to_model = user_text

    if lang == "kannada":
        # Apply LEFT->RIGHT to the user input (this ensures the model sees your Kannada tokens)
        prompt_to_model, replacements_input = apply_left_to_right(user_text, pairs)

    if use_model:
        if not api_key:
            return jsonify({"error":"missing_api_key"}), 400
        # call model with the (possibly replaced) prompt_to_model
        raw, info = ask_groq(prompt_to_model, lang, api_key)
        if raw is None:
            return jsonify({"error":"model_failed","detail":info}), 500
        source_text = raw
        source_info = {"from":"model", "info": info}
    else:
        source_text = prompt_to_model
        source_info = {"from":"user_input"}

    # Optionally, apply replacements again to model output (keeps strict CSV behavior)
    final_text, replacements_final = (source_text, [])
    if lang == "kannada":
        final_text, replacements_final = apply_left_to_right(source_text, pairs)

    return jsonify({
        "input_text": user_text,
        "prompt_sent_to_model": prompt_to_model if use_model else None,
        "source_text": source_text,
        "final_text": final_text,
        "replacements_input": replacements_input,   # what was changed in the user input before model
        "replacements_final": replacements_final,   # what (if anything) replaced in model output
        "csv_pairs_loaded": len(pairs),
        "source_info": source_info
    })

if __name__=="__main__":
    print(f"Running → http://127.0.0.1:{PORT} (CSV: {CSV_NAME})")
    app.run(port=PORT, debug=True)