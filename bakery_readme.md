# 🍰 Sweet Delights Bakery

An AI-powered bakery e-commerce application built with Streamlit, featuring MCP (Model Context Protocol) server integration and Ollama LLM for intelligent product recommendations and customer assistance.

## Features

- **Product Browsing**: Browse bakery products with filtering by category, price, and dietary restrictions
- **AI Assistant**: Chat with an intelligent bakery assistant powered by Ollama LLM
- **Shopping Cart**: Add products to cart and manage orders
- **MCP Integration**: Backend server handling product data and AI interactions
- **Real-time Chat**: Interactive chat interface with chat history

## Prerequisites

- **Python 3.10+** (Python 3.13.5 recommended)
- **macOS** (instructions provided for Mac, adaptable for other systems)
- **Homebrew** (for installing Ollama)

## Installation & Setup

### 1. Clone or Download the Project

Ensure you have these files in your project directory:
```
your_project_folder/
├── mcp_bakery_server.py
├── streamlit_bakery_app.py
├── requirements.txt
└── README.md
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### 3. Install Ollama

```bash
# Install Ollama using Homebrew
brew install ollama

# Alternative: Download from https://ollama.com/download
```

### 4. Download AI Model

```bash
# Start Ollama service (keep this running)
ollama serve
```

In a **new terminal window**:
```bash
# Download the lightweight model for testing
ollama pull tinyllama:latest

# Optional: Download more capable models
ollama pull llama3.2:1b      # Faster, smaller (1.3GB)
ollama pull llama3.2:3b      # Better quality (2GB)

# Test the model
ollama run tinyllama:latest
```

Type "Hello" to test, then type `/bye` to exit.

## Running the Application

### 1. Start Ollama Service

```bash
# In terminal window 1
ollama serve
```

Keep this running throughout your session.

### 2. Start the Streamlit Application

```bash
# In terminal window 2
# Make sure you're in your project directory and virtual environment is activated
source venv/bin/activate
streamlit run streamlit_bakery_app.py
```

### 3. Access the Application

- **Streamlit App**: http://localhost:8501
- **Ollama API**: http://localhost:11434 (background service)

## Application Structure

### Pages

1. **Browse Products**
   - View all bakery products
   - Filter by category, price, and dietary restrictions
   - Add items to shopping cart

2. **AI Assistant**
   - Chat with AI bakery assistant
   - Get product recommendations
   - Search for specific items
   - Ask questions about products

3. **Shopping Cart**
   - View added items
   - Remove items
   - Proceed to checkout (demo)

### Key Components

- **MCP Server** (`mcp_bakery_server.py`): Handles product data and AI interactions
- **Streamlit App** (`streamlit_bakery_app.py`): Frontend interface
- **Ollama Integration**: Provides LLM capabilities for the AI assistant


## Configuration

### Environment Variables

You can customize the Ollama integration by setting these environment variables:

```bash
# Ollama API endpoint (default: http://localhost:11434/api/generate)
export OLLAMA_API_URL="http://localhost:11434/api/generate"

# Ollama model to use (default: tinyllama:latest)
export OLLAMA_MODEL="llama3.2:1b"
```

### Model Recommendations

| Model | Size | Use Case |
|-------|------|----------|
| `tinyllama:latest` | ~700MB | Testing, development |
| `llama3.2:1b` | 1.3GB | Fast responses, good quality |
| `llama3.2:3b` | 2GB | Better understanding, slower |
| `codellama:7b` | 3.8GB | Advanced capabilities |

## Troubleshooting

### Common Issues

**1. "zsh: command not found: ollama"**
```bash
# Reinstall Ollama
brew install ollama
# Or download from https://ollama.com/download
```

**2. MCP Connection Failed (🔴 Status)**
- Check if Ollama is running: `ollama serve`
- Verify model is downloaded: `ollama list`
- App will use mock data as fallback

**3. "Could not find a version that satisfies the requirement mcp>=1.0.0"**
- Ensure Python 3.10+ is being used
- Recreate virtual environment with correct Python version

**4. Port Already in Use**
```bash
# Find and kill process using port 8501
lsof -ti:8501 | xargs kill -9

# Restart Streamlit
streamlit run streamlit_bakery_app.py
```

### Checking System Status

```bash
# Check Python version
python --version

# Check installed packages
pip list

# Check Ollama models
ollama list

# Check if Ollama is running
curl http://localhost:11434/api/tags
```


### File Structure

```
├── mcp_bakery_server.py       # MCP server with product data & AI logic
├── streamlit_bakery_app.py    # Streamlit frontend application
├── requirements.txt           # Python dependencies
└── README.md                 # This file
```

### Key Dependencies

- `streamlit>=1.28.0` - Web application framework
- `mcp>=1.0.0` - Model Context Protocol
- `requests>=2.31.0` - HTTP requests for Ollama API
- `pandas>=2.0.0` - Data manipulation
- `pydantic>=2.0.0` - Data validation

### Adding New Products

Products are defined in `mcp_bakery_server.py` in the `PRODUCTS_DATA` list. Each product should have:

```python
{
    "id": unique_id,
    "name": "Product Name",
    "description": "Product description",
    "price": float_price,
    "category": "Category",
    "rating": float_rating,
    "stock_quantity": int_quantity,
    "image_url": "emoji",
    "dietary_info": ["list", "of", "dietary", "tags"]
}
```

