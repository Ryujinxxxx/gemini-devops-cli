# Gemini DevOps CLI

A terminal-first Gemini assistant for AWS, Kubernetes, Linux, config review, and real-time web-grounded analysis.

## Features

- Interactive chat mode
- AWS, Kubernetes, Linux, and review modes
- Google Search grounding for fresher answers
- Local file analysis
- URL fetch and analysis
- Local shell command output analysis
- Saved chat history
- Optional second-pass answer refinement

## Why this version

This project uses the Google GenAI SDK, which Google documents as the recommended production library, and defaults to `gemini-2.5-flash`, a stable Gemini model positioned for low-latency, high-volume, price-performance workloads. It also supports Google Search grounding for real-time web content. See the official docs for details:

- Google GenAI SDK GA and recommended libraries
- `gemini-2.5-flash` model page
- Google Search grounding

## Project structure

```text
.
├── gemini_cli.py
├── requirements.txt
├── .gitignore
├── LICENSE
├── README.md
├── examples
│   ├── deployment.yaml
│   └── sample.log
├── docs
│   └── ROADMAP.md
└── scripts
    └── install.sh
```

## Requirements

- Python 3.10+
- A Gemini API key in `GEMINI_API_KEY`
- `curl` available in your shell for `--web`

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/your-username/gemini-devops-cli.git
cd gemini-devops-cli
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Export your API key

```bash
export GEMINI_API_KEY="your_actual_key"
```

### 5. Install the CLI locally

```bash
bash scripts/install.sh
source ~/.bashrc
hash -r
```

### 6. Test it

```bash
gemini --help
gemini "Explain BGP in simple words"
```

## Usage

### Basic

```bash
gemini "Explain Kubernetes Service"
```

### Chat mode

```bash
gemini --chat
```

### Grounded web search

```bash
gemini --ground "latest AWS news"
```

### AWS mode

```bash
gemini --mode aws "Design a secure low-cost VPC for a small app"
```

### Kubernetes file review

```bash
gemini --mode k8s --file examples/deployment.yaml "Review this manifest"
```

### Linux command output analysis

```bash
gemini --mode linux --cmd "uname -a && free -h && df -h" "Summarize this server state"
```

### URL fetch and summarize

```bash
gemini --web https://aws.amazon.com/blogs/aws/ "Summarize recent updates"
```

### Piped input

```bash
echo "CrashLoopBackOff after liveness probe failures" | gemini --mode k8s "Analyze this output"
```

### Optional refinement

```bash
gemini --refine "Explain BGP in simple words"
```

## Chat commands

Inside `gemini --chat`:

```text
/help
/mode default|k8s|aws|linux|review
/stream
/ground
/refine
/clear
/save
/exit
```

## Security notes

- Never commit your API key.
- `--cmd` executes a local shell command. Only use commands you trust.
- `--web` uses `curl` and sends fetched content to Gemini.

## GitHub repo setup checklist

- Add your actual GitHub URL in this README after pushing.
- Add screenshots or terminal demos if you want a stronger portfolio presentation.
- Consider GitHub Actions linting in a future revision.

## License

MIT
