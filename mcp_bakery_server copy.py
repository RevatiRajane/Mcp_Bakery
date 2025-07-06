#!/usr/bin/env python3
"""
MCP Bakery Server
Responds to JSON-RPC requests from a client (e.g., Streamlit Bakery App)
to provide product information and recommendations, now with LLM integration.
"""

import sys
import json
import logging
import os
import requests 
import re 

# --- Server Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - MCP_SERVER - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "tinyllama:latest") 
OLLAMA_TIMEOUT = 30 

# --- Bakery Data ---
PRODUCTS_DATA = [
    {
        "id": 1, "name": "Classic Chocolate Cake", "description": "Rich and moist chocolate cake, perfect for celebrations.",
        "price": 25.99, "category": "Cakes", "rating": 4.8, "stock_quantity": 15,
        "image_url": "🎂", "dietary_info": ["contains gluten", "contains dairy", "vegetarian"]
    },
    {
        "id": 2, "name": "Vanilla Bean Cupcakes (6-pack)", "description": "Fluffy vanilla cupcakes with creamy buttercream frosting.",
        "price": 18.00, "category": "Cupcakes", "rating": 4.5, "stock_quantity": 30,
        "image_url": "🧁", "dietary_info": ["contains gluten", "contains dairy", "vegetarian"]
    },
    {
        "id": 3, "name": "Artisan Sourdough Bread", "description": "Authentic, crusty sourdough bread with a delightful tangy flavor.",
        "price": 8.50, "category": "Breads", "rating": 4.9, "stock_quantity": 20,
        "image_url": "🍞", "dietary_info": ["contains gluten", "vegan"]
    },
    {
        "id": 4, "name": "Almond Croissants (Pair)", "description": "Buttery, flaky croissants filled with rich almond paste and topped with sliced almonds.",
        "price": 7.00, "category": "Pastries", "rating": 4.7, "stock_quantity": 0, 
        "image_url": "🥐", "dietary_info": ["contains gluten", "contains dairy", "contains nuts", "vegetarian"]
    },
    {
        "id": 5, "name": "Blueberry Muffins (4-pack)", "description": "Moist and tender muffins packed with juicy blueberries.",
        "price": 12.00, "category": "Muffins", "rating": 4.3, "stock_quantity": 18,
        "image_url": "🫐", "dietary_info": ["contains gluten", "contains dairy", "vegetarian"]
    },
    {
        "id": 6, "name": "Vegan Chocolate Chip Cookies (Dozen)", "description": "Deliciously soft and chewy vegan cookies, loaded with chocolate chips.",
        "price": 22.00, "category": "Cookies", "rating": 4.6, "stock_quantity": 22,
        "image_url": "🍪", "dietary_info": ["contains gluten", "vegan"]
    },
    {
        "id": 7, "name": "Gluten-Free Brownie Bites (Box of 8)", "description": "Intensely fudgy and rich gluten-free brownie bites for a decadent treat.",
        "price": 15.00, "category": "Brownies", "rating": 4.4, "stock_quantity": 12,
        "image_url": "🍫", "dietary_info": ["gluten-free", "contains dairy", "vegetarian"]
    },
    {
        "id": 8, "name": "Raspberry Danish", "description": "Flaky pastry with a sweet cream cheese and raspberry filling.",
        "price": 4.50, "category": "Pastries", "rating": 4.5, "stock_quantity": 10,
        "image_url": "🍓", "dietary_info": ["contains gluten", "contains dairy", "vegetarian"]
    },
]
CATEGORIES_DATA = sorted(list(set(p["category"] for p in PRODUCTS_DATA)))


# --- Helper Functions ---
def send_response(response_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": response_id}
    if result is not None: message["result"] = result
    if error is not None: message["error"] = error
    json_message = json.dumps(message)
    logger.debug(f"MCP_SERVER: Sending response: {json_message[:500]}")
    print(json_message, flush=True)

def create_error_response(code, message, data=None):
    error_obj = {"code": code, "message": message}
    if data: error_obj["data"] = data
    return error_obj

def format_tool_call_response_content(data_payload):
    return {"content": [{"type": "text", "text": json.dumps(data_payload)}]}

def format_resource_read_response_content(data_payload):
    return {"contents": [{"type": "text", "text": json.dumps(data_payload)}]}

def format_items_for_chatbot_response(items_data: list, prefix: str) -> str:
    if isinstance(items_data, dict) and "error" in items_data: # Tool itself might return an error structure
        return f"Sorry, I encountered an error with an item: {items_data['error']}"
    if not items_data or not isinstance(items_data, list):
        return "I couldn't find any matching items right now."
    response_str = prefix
    for i, item in enumerate(items_data[:3], 1): 
        response_str += f"{i}. **{item.get('name', 'N/A')}** {item.get('image_url', '')} - ${item.get('price', 0.0):.2f}\n"
        desc = item.get('description', 'No description available.')
        response_str += f"   {desc[:80]}{'...' if len(desc) > 80 else ''}\n"
        rating = item.get('rating', 0)
        if rating > 0:
            response_str += f"   Rating: {'⭐' * int(rating)} ({rating}/5)\n"
    if len(items_data) > 3:
        response_str += f"...and {len(items_data) - 3} more items."
    return response_str

# --- Tool Implementations ---
def get_popular_products(arguments=None): 
    limit = arguments.get("limit", 3) if arguments else 3
    sorted_products = sorted(PRODUCTS_DATA, key=lambda p: (p.get("rating", 0), p.get("stock_quantity", 0)), reverse=True)
    return sorted_products[:limit]

def get_product_recommendations(arguments):
    preferences = arguments.get("preferences", {})
    dietary_restrictions = [r.lower() for r in preferences.get("dietary_restrictions", [])]
    category_pref = preferences.get("category", "").lower()
    recommended = []
    for product in PRODUCTS_DATA:
        if product.get("stock_quantity", 0) == 0: continue
        matches_dietary = True
        if dietary_restrictions:
            product_diet_info = [info.lower() for info in product.get("dietary_info", [])]
            for restriction in dietary_restrictions:
                if restriction not in product_diet_info:
                    matches_dietary = False; break
        matches_category = True
        if category_pref and product.get("category", "").lower() != category_pref:
            matches_category = False
        if matches_dietary and matches_category: recommended.append(product)
    return recommended[:5]

def search_products(arguments):
    query_string = arguments.get("query", "").lower()
    if not query_string:
        return []

    query_terms = query_string.split() # Split into individual terms, e.g., ["vegan", "bread"]
    if not query_terms:
        return []

    results = []
    for product in PRODUCTS_DATA:
        product_name_lower = product.get("name", "").lower()
        product_desc_lower = product.get("description", "").lower()
        product_cat_lower = product.get("category", "").lower()
        product_dietary_lower = [di.lower() for di in product.get("dietary_info", [])]

        match_count = 0
        for term in query_terms:
            term_matched_in_product = False
            if term in product_name_lower:
                term_matched_in_product = True
            elif term in product_desc_lower:
                term_matched_in_product = True
            elif term in product_cat_lower:
                term_matched_in_product = True
            else:
                # Check if the term matches any of the dietary info tags
                for dietary_tag in product_dietary_lower:
                    if term in dietary_tag: # e.g., "vegan" in "vegan"
                        term_matched_in_product = True
                        break # Found in dietary, no need to check other tags for this term
            
            if term_matched_in_product:
                match_count += 1

        # If all terms in the query are found somewhere in the product's info
        if match_count == len(query_terms):
            results.append(product)
            
    return results
def get_product_details(arguments):
    product_id = arguments.get("product_id")
    if product_id is None: return {"error": "Missing product_id parameter"}
    try: product_id = int(product_id)
    except ValueError: return {"error": "Invalid product_id format"}
    for product in PRODUCTS_DATA:
        if product.get("id") == product_id: return product
    return {"error": "Product not found", "id": product_id}

# --- Ollama LLM Interaction ---
def query_ollama_llm(prompt: str, chat_history: list = None):
    full_prompt = "You are a friendly and helpful AI assistant for 'Sweet Delights Bakery'. Keep your responses concise and focused on bakery-related topics. Do not make up items not in the bakery's inventory. If you don't know something, say so. Do not ask me to search for you.\n"
    if chat_history:
        for entry in chat_history[-2:]:
            if entry.get("role") == "user":
                full_prompt += f"\nUser: {entry.get('content')}"
            elif entry.get("role") == "assistant":
                full_prompt += f"\nAssistant: {entry.get('content')}"
    full_prompt += f"\nUser: {prompt}\nAssistant:"

    payload = {
        "model": OLLAMA_MODEL, 
        "prompt": full_prompt,
        "stream": False, 
        "options": { "num_ctx": 2048, "temperature": 0.6, "top_p": 0.9, }
    }
    logger.info(f"MCP_SERVER: Sending to Ollama (model: {OLLAMA_MODEL}): {json.dumps(payload, indent=2)[:300]}...")
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status() 
        response_data = response.json()
        llm_response_text = response_data.get("response", "Sorry, I couldn't generate a response right now.").strip()
        logger.info(f"MCP_SERVER: Ollama raw response: {llm_response_text[:300]}")
        return llm_response_text
    except requests.exceptions.RequestException as e:
        logger.error(f"MCP_SERVER: Ollama request failed: {e}")
        return f"Sorry, I'm having trouble connecting to my AI brain. Error: {type(e).__name__}"
    except json.JSONDecodeError as e:
        logger.error(f"MCP_SERVER: Ollama response JSON decode error: {e}. Response text: {response.text}")
        return "Sorry, I received an unexpected response from my AI brain."

# --- START: assistant_chat Tool Function ---
def assistant_chat(arguments):
    user_input = arguments.get("user_input", "").lower()
    chat_history = arguments.get("chat_history", []) 
    logger.info(f"MCP_SERVER: assistant_chat received input: '{user_input}'")

    if any(word in user_input for word in ['hello', 'hi', 'hey']):
        return {"response_text": "Hello! Welcome to our AI Bakery Assistant! 🍰 How can I help you today?"}
    if "popular" in user_input or "bestseller" in user_input:
        popular_items_data = get_popular_products() # Call the function
        response_text = format_items_for_chatbot_response(popular_items_data, "Our most popular items are:\n")
        return {"response_text": response_text}
    if "details for product id" in user_input:
        try:
            product_id_str = user_input.split('details for product id')[-1].strip()
            product_id = int(product_id_str)
            details_data = get_product_details({"product_id": product_id}) # Call the function
            if isinstance(details_data, dict) and "error" not in details_data:
                 response_text = format_items_for_chatbot_response([details_data], f"Details for Product ID {product_id}:\n")
            else: # details_data itself is an error dict
                response_text = f"Could not find details for product ID {product_id}. Error: {details_data.get('error', 'Unknown')}"
            return {"response_text": response_text}
        except ValueError: return {"response_text": "Please provide a valid numeric product ID."}
        except Exception as e: return {"response_text": f"Error fetching product details: {e}"}

    search_match = re.search(r"\b(search|find)\b(?: for)?\s*(.+)", user_input, re.IGNORECASE)
    if search_match:
        query = search_match.group(2).strip()
        if query:
            search_results_data = search_products({"query": query}) # Call the function
            response_text = format_items_for_chatbot_response(search_results_data, f"I found these items matching '{query}':\n")
            return {"response_text": response_text}
        else: return {"response_text": "What would you like me to search for?"}

    recommend_match = re.search(r"\b(recommend|suggest|suggestion)\b(?: for)?\s*(.+)?", user_input, re.IGNORECASE)
    if recommend_match:
        prefs_text = recommend_match.group(2) if recommend_match.group(2) else ""
        preferences = {}
        if 'vegan' in prefs_text: preferences.setdefault('dietary_restrictions', []).append('vegan')
        if 'gluten' in prefs_text or 'gluten-free' in prefs_text: preferences.setdefault('dietary_restrictions', []).append('gluten-free')
        all_categories_server = sorted(list(set(item["category"].lower() for item in PRODUCTS_DATA)))
        found_category = next((cat for cat in all_categories_server if cat in prefs_text), None)
        if found_category: preferences['category'] = found_category
        recommendations_data = get_product_recommendations({"preferences": preferences}) # Call the function
        prefix = "Based on your preferences, I recommend:\n" if preferences else "Here are some general recommendations:\n"
        response_text = format_items_for_chatbot_response(recommendations_data, prefix)
        return {"response_text": response_text}
        
    logger.info(f"MCP_SERVER: No specific keyword matched for '{user_input}'. Querying LLM.")
    llm_response = query_ollama_llm(user_input, chat_history)
    return {"response_text": llm_response}
# --- END: assistant_chat Tool Function ---

# --- Tool Registry ---
TOOLS = {
    "get_popular_products": get_popular_products,
    "get_product_recommendations": get_product_recommendations,
    "search_products": search_products,
    "get_product_details": get_product_details,
    "assistant_chat": assistant_chat, # Ensure this key matches what the client calls
}

# --- Resource Implementations ---
def read_products_all(uri_params=None): return PRODUCTS_DATA
def read_products_categories(uri_params=None): return CATEGORIES_DATA
RESOURCES = {
    "bakery://products/all": read_products_all,
    "bakery://products/categories": read_products_categories,
}

# --- Request Handler ---
def handle_request(request_obj):
    req_id = request_obj.get("id")
    method = request_obj.get("method")
    params = request_obj.get("params", {})

    if not method:
        if req_id: send_response(req_id, error=create_error_response(-32600, "Invalid Request: Missing method"))
        return
    logger.info(f"MCP_SERVER: Received method: {method}, params: {json.dumps(params)[:200]}")

    if method == "initialize":
        server_capabilities = {
            "experimental": { # Simplified for clarity
                "bakeryTools": True, 
                "assistantChat": True # Capability for the new tool
            }
        }
        send_response(req_id, result={"capabilities": server_capabilities})
    elif method == "initialized":
        logger.info("MCP_SERVER: Client initialized notification received.")
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_arguments = params.get("arguments", {})
        logger.info(f"MCP_SERVER: Attempting to call tool: '{tool_name}'")
        if tool_name in TOOLS:
            try:
                # The tool function (e.g. assistant_chat) returns a dict like {"response_text": "..."}
                # or for older tools, a list/dict of data.
                tool_result_data = TOOLS[tool_name](tool_arguments)
                
                # format_tool_call_response_content expects the data payload that will be JSON stringified.
                # For assistant_chat, tool_result_data is already {"response_text": "..."}.
                # For other tools, tool_result_data is the raw list/dict (e.g., list of products).
                # This is fine, json.dumps in format_tool_call_response_content handles both.
                formatted_result_for_client = format_tool_call_response_content(tool_result_data)
                send_response(req_id, result=formatted_result_for_client)
            except Exception as e:
                logger.error(f"MCP_SERVER: Error executing tool {tool_name}: {e}", exc_info=True)
                send_response(req_id, error=create_error_response(-32000, f"Server error executing tool {tool_name}: {str(e)}"))
        else:
            logger.error(f"MCP_SERVER: Tool not found: '{tool_name}'. Available tools: {list(TOOLS.keys())}")
            send_response(req_id, error=create_error_response(-32601, f"Tool not found: {tool_name}")) # -32601 Method not found
    
    elif method == "resources/read":
        uri = params.get("uri")
        if uri in RESOURCES:
            try:
                resource_data = RESOURCES[uri]()
                formatted_data = format_resource_read_response_content(resource_data)
                send_response(req_id, result=formatted_data)
            except Exception as e:
                logger.error(f"MCP_SERVER: Error reading resource {uri}: {e}", exc_info=True)
                send_response(req_id, error=create_error_response(-32000, f"Server error reading resource {uri}: {str(e)}"))
        else:
            send_response(req_id, error=create_error_response(-32601, f"Resource not found: {uri}"))
    elif method == "shutdown":
        logger.info("MCP_SERVER: Shutdown request received. Preparing to exit.")
        if req_id: send_response(req_id, result=None) # Acknowledge
    elif method == "exit":
        logger.info("MCP_SERVER: Exit notification received. Terminating server.")
        sys.exit(0) 
    else:
        if req_id: send_response(req_id, error=create_error_response(-32601, f"Method not found: {method}"))
        logger.warning(f"MCP_SERVER: Unknown method received: {method}")

# --- Main Server Loop ---
def main():
    logger.info("MCP_SERVER: MCP Bakery Server (with LLM) started. Listening on stdin...")
    logger.info(f"MCP_SERVER: PID: {os.getpid()}")
    logger.info(f"MCP_SERVER: Ollama API URL: {OLLAMA_API_URL}, Model: {OLLAMA_MODEL}")
    logger.info(f"MCP_SERVER: Registered tools: {list(TOOLS.keys())}") # CRITICAL: Check this log
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                logger.info("MCP_SERVER: Stdin closed. Exiting.")
                break 
            line = line.strip()
            if not line: continue
            logger.debug(f"MCP_SERVER: Received raw line: {line[:500]}")
            try: request_obj = json.loads(line)
            except json.JSONDecodeError: 
                logger.error(f"MCP_SERVER: Failed to decode JSON: {line}")
                continue
            handle_request(request_obj)
    except KeyboardInterrupt:
        logger.info("MCP_SERVER: Server interrupted by KeyboardInterrupt. Exiting.")
    except Exception as e:
        logger.error(f"MCP_SERVER: Unhandled exception in main loop: {e}", exc_info=True)
    finally:
        logger.info("MCP_SERVER: MCP Bakery Server shutting down.")

if __name__ == "__main__":
    main()