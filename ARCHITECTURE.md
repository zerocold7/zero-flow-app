# Local Voice Flow — System Architecture Blueprint

This document explains the internal data pipelines and execution lifecycle of the Local Voice Flow engine for developers and collaborators.

---

## 1. High-Level Core Pipeline
When a user interacts with the system, data flows through three distinct infrastructure layers: Hardware Capture, Neural Transcription, and LLM Post-Processing.

 [User Audio Input] 
        │
        ▼
 ┌────────────────────────────────────────────────────────┐
 │ 1. HARDWARE LAYER (sounddevice Engine)                 │
 │    - Samples at 16,000Hz, Mono Channel                 │
 │    - Automatic Driver Check (NVIDIA CUDA Core vs CPU)   │
 └────────────────────────────────────────────────────────┘
        │
        ▼  (Temporary .wav Buffer Allocation)
 ┌────────────────────────────────────────────────────────┐
 │ 2. TRANSCRIPTION LAYER (faster-whisper Engine)         │
 │    - Loads 'large-v3' Neural Weights                   │
 │    - Injects Live Clipboard Context & Vocab Hints      │
 └────────────────────────────────────────────────────────┘
        │
        ▼  (Raw Text String Generation)
 ┌────────────────────────────────────────────────────────┐
 │ 3. REFINEMENT & INJECTION LAYER (Ollama & Keyboard)    │
 │    - Raw Mode: Immediate Injection via Simulated OS    │
 │    - Polish Mode: Contextual API Round-trip to Ollama  │
 └────────────────────────────────────────────────────────┘
        │
        ▼
 [Active Windows Application Cursor Target]

---

## 2. Infrastructure Layer Breakdowns

### A. Hardware Initialization & Fallback Policy
On application boot via `Launch_Flow.bat`, the engine executes an environmental verification scan:
1. **OS Constraint Check:** Verifies system platform build matching Windows 11 targets. Aborts execution if requirements are unfulfilled.
2. **NVIDIA DLL Scanner:** Scans local Python paths to dynamically bind `cublas` and `cudnn` binary trees directly to the active environment pathing.
3. **Hardware Fallback Switch:** - Attempts binding `WhisperModel` weights onto `device="cuda"` utilizing `float16` precision.
   - If driver hooks fail, it catches the runtime exception and safely steps down execution to CPU space using optimized `int8` quantization. This preserves host laptop memory allocations.

### B. Dynamic LLM API Resolution
The engine completely decouples itself from hardcoded model requirements:
* On initialization, it fires a silent `GET` packet to the local Ollama API sub-system (`/api/tags`).
* It parses the JSON payload array and automatically binds the engine's text-refinement tasks to the first locally cached or currently serving model weight it discovers.
* If Ollama is non-responsive or offline, it safely switches to a fail-safe configuration string without throwing fatal faults.

### C. Context Enrichment & Lexicon Adaptation
Unlike static dictation software, this system uses dual-source semantic context modeling before processing transcription inputs:
* **Clipboard Context Sniffer:** Right before recording starts, the script reads a snippet from the Windows clipboard (`pyperclip`, with URLs stripped) and passes it to the Ollama refinement step in Polish mode as contextual grounding. It is deliberately kept *out* of the Whisper prompt — which now carries only the vocabulary term list — so that an English clipboard can no longer bias Arabic speech toward English output.
* **Self-Evolving Memory System (`flow_vocabulary.txt`):** The engine tracks custom vocabulary arrays. If the active Ollama model identifies an unrecognized proper name or specific technical term, it uses a custom regex parser to catch the text, strip it out, and permanently save the term to a local text index file. This file updates the vocabulary arrays during subsequent voice capture passes.

### D. Smart Macro Control Logic
The injection layer strips away structural commands from natural speaking patterns on-the-fly. Spoken tokens such as `"new line"`, `"bullet"`, and `"format code"` are extracted from the finalized text stream via string alignment scripts, translated into programmatic virtual keyboard strikes (e.g., `shift+enter` or inline backtick wrappers), and injected directly at the active UI cursor target.