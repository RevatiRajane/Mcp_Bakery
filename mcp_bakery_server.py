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
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b") 
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
    user_input_original = arguments.get("user_input", "") # Keep original case for LLM if needed
    user_input_lower = user_input_original.lower()
    chat_history = arguments.get("chat_history", []) 
    logger.info(f"MCP_SERVER: assistant_chat received input: '{user_input_original}'")

    # --- LLM Decides on Tool ---
    llm_decision = query_llm_for_tool_choice(user_input_original, chat_history)
    
    chosen_tool_name = llm_decision.get("tool_name")
    tool_args = llm_decision.get("arguments", {})

    if chosen_tool_name and chosen_tool_name != "no_tool" and chosen_tool_name in TOOLS:
        logger.info(f"MCP_SERVER: LLM chose tool: '{chosen_tool_name}' with args: {tool_args}")
        try:
            # Execute the chosen tool (ensure tool_args are what the tool expects)
            # Individual tool functions (get_popular_products, etc.) expect `arguments` as their top-level param.
            # The LLM is set up to return an `arguments` object directly.
            tool_function = TOOLS[chosen_tool_name]
            tool_result_data = tool_function(tool_args) # Pass the 'arguments' dict from LLM directly

            # Now, format this tool_result_data into a natural language response.
            # This step could also involve another LLM call to synthesize the response.
            # For simplicity, we'll reuse some of the previous formatting logic.
            response_text = ""
            if chosen_tool_name == "get_popular_products":
                response_text = format_items_for_chatbot_response(tool_result_data, "Our most popular items are:\n")
            elif chosen_tool_name == "search_products":
                query_display = tool_args.get("query", user_input_original) # Use extracted query or original
                response_text = format_items_for_chatbot_response(tool_result_data, f"I found these items matching '{query_display}':\n")
            elif chosen_tool_name == "get_product_recommendations":
                response_text = format_items_for_chatbot_response(tool_result_data, "Based on your preferences, I recommend:\n")
            elif chosen_tool_name == "get_product_details":
                product_id_display = tool_args.get("product_id", "the requested ID")
                if isinstance(tool_result_data, dict) and "error" in tool_result_data:
                    response_text = f"Could not find details for product ID {product_id_display}. Error: {tool_result_data.get('error', 'Unknown')}"
                else:
                    response_text = format_items_for_chatbot_response([tool_result_data], f"Details for Product ID {product_id_display}:\n") # Wrap in list for formatter
            else: # Should not happen if chosen_tool_name is in TOOLS
                response_text = json.dumps(tool_result_data) # Generic fallback

            return {"response_text": response_text}

        except Exception as e:
            logger.error(f"MCP_SERVER: Error executing tool '{chosen_tool_name}' chosen by LLM: {e}", exc_info=True)
            # Fallback to direct LLM response on tool execution error
            llm_response = query_ollama_llm(user_input_original, chat_history) # General LLM call
            return {"response_text": f"I tried to use a tool but encountered an error. Here's a general response instead: {llm_response}"}
    else:
        # No tool chosen, or 'no_tool' returned by LLM, or invalid tool name
        reason = tool_args.get("reason", "No specific tool seemed appropriate.")
        logger.info(f"MCP_SERVER: No tool chosen by LLM (or invalid tool '{chosen_tool_name}'). Reason: {reason}. Falling back to direct LLM response.")
        llm_response = query_ollama_llm(user_input_original, chat_history) # General LLM call
        return {"response_text": llm_response}


# --- Tool Registry ---
TOOLS = {
    "get_popular_products": get_popular_products,
    "get_product_recommendations": get_product_recommendations,
    "search_products": search_products,
    "get_product_details": get_product_details,
    "assistant_chat": assistant_chat, # Ensure this key matches what the client calls
}


TOOL_DESCRIPTIONS = [
    {
        "name": "get_popular_products",
        "description": "Fetches a list of the most popular products. Use if the user asks for popular, best-selling, or top items.",
        "parameters": [
            {"name": "limit", "type": "integer", "description": "Optional. Number of popular products to return (default 3)."}
        ]
    },
    {
        "name": "search_products",
        "description": "Searches for products based on a query string. Use if the user wants to find or search for specific items by name, description, category, or dietary information.",
        "parameters": [
            {"name": "query", "type": "string", "description": "The search term(s). E.g., 'chocolate cake', 'vegan cookies'."}
        ]
    },
    {
        "name": "get_product_recommendations",
        "description": "Recommends products based on user preferences like category or dietary restrictions. Use if the user asks for recommendations or suggestions.",
        "parameters": [
            {"name": "preferences", "type": "object", "description": "An object containing preferences.",
             "properties": {
                 "category": {"type": "string", "description": "E.g., 'Cakes', 'Cookies', 'Breads'."},
                 "dietary_restrictions": {"type": "array", "items": {"type": "string"}, "description": "E.g., ['vegan', 'gluten-free']"}
             }}
        ]
    },
    {
        "name": "get_product_details",
        "description": "Fetches detailed information for a specific product given its ID. Use if the user asks for details of a product ID.",
        "parameters": [
            {"name": "product_id", "type": "integer", "description": "The unique ID of the product."}
        ]
    }
]

def generate_tool_selection_prompt(user_query: str, chat_history: list = None):
    prompt = f"""You are an AI assistant for a bakery. Your task is to analyze the user's query and decide which, if any, of the available tools can best address it.
If a tool is appropriate, respond with a JSON object containing the 'tool_name' and any necessary 'arguments' extracted from the query.
If no tool is suitable, respond with JSON: {{"tool_name": "no_tool", "arguments": {{"reason": "brief explanation why no tool is needed"}}}}
Do not add any explanations outside of the JSON.

Available tools:
"""
    for tool in TOOL_DESCRIPTIONS:
        prompt += f"- Tool Name: {tool['name']}\n"
        prompt += f"  Description: {tool['description']}\n"
        if tool.get('parameters'):
            prompt += f"  Parameters:\n"
            for param in tool['parameters']:
                prompt += f"    - {param['name']} ({param['type']}): {param['description']}\n"
                if 'properties' in param: # For object parameters
                    for prop_name, prop_details in param['properties'].items():
                        prompt += f"      - {prop_name} ({prop_details['type']}): {prop_details['description']}\n"
        prompt += "\n"

    # Basic history inclusion
    if chat_history:
        for entry in chat_history[-2:]: # Last 2 exchanges
            if entry.get("role") == "user":
                prompt += f"Previous User: {entry.get('content')}\n"
            elif entry.get("role") == "assistant":
                prompt += f"Previous Assistant: {entry.get('content')}\n"
    
    prompt += f"\nUser Query: \"{user_query}\"\n"
    prompt += "JSON Response (tool_name and arguments OR no_tool):"
    return prompt


def query_llm_for_tool_choice(user_query: str, chat_history: list = None):
    prompt = generate_tool_selection_prompt(user_query, chat_history)
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json", # Request JSON output
        "options": {"temperature": 0.1, "top_p": 0.7, "num_ctx": 2048} # Even lower temp
    }
    logger.info(f"MCP_SERVER: Sending tool selection prompt to LLM (model: {OLLAMA_MODEL}): {prompt[:500]}...")
    try:
        ollama_response = requests.post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        ollama_response.raise_for_status()
        
        # The entire response from Ollama when format="json" is a JSON object (Python dict after .json())
        ollama_data = ollama_response.json()
        logger.info(f"MCP_SERVER: Full Ollama raw response object for tool choice: {ollama_data}")

        # The LLM's actual generated text (which should be JSON) is in the "response" field
        llm_generated_json_string = ollama_data.get("response")

        if not llm_generated_json_string:
            logger.error("MCP_SERVER: LLM did not provide a 'response' field for tool choice.")
            return {"tool_name": "no_tool", "arguments": {"reason": "LLM response was empty."}}

        logger.info(f"MCP_SERVER: LLM-generated string (expected to be JSON) for tool choice: {llm_generated_json_string}")
        
        try:
            # Now parse THIS string
            llm_decision = json.loads(llm_generated_json_string)
            logger.info(f"MCP_SERVER: LLM successfully parsed decision: {llm_decision}")
            return llm_decision
        except json.JSONDecodeError as je:
            logger.error(f"MCP_SERVER: Failed to parse LLM's actual 'response' string as JSON: {je}. String was: {llm_generated_json_string}")
            # Attempt to extract JSON even if there's surrounding text (common issue)
            try:
                json_start = llm_generated_json_string.find('{')
                json_end = llm_generated_json_string.rfind('}')
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_str_cleaned = llm_generated_json_string[json_start : json_end+1]
                    llm_decision_cleaned = json.loads(json_str_cleaned)
                    logger.info(f"MCP_SERVER: LLM decision parsed after cleanup: {llm_decision_cleaned}")
                    return llm_decision_cleaned
                else:
                    raise je # Re-raise original error if cleanup fails
            except Exception as e_clean:
                logger.error(f"MCP_SERVER: Cleanup of LLM JSON string also failed: {e_clean}")
                return {"tool_name": "no_tool", "arguments": {"reason": f"LLM response was not valid JSON: {llm_generated_json_string[:100]}"}}

    except requests.exceptions.RequestException as e:
        logger.error(f"MCP_SERVER: Ollama request for tool choice failed: {e}")
        return {"tool_name": "no_tool", "arguments": {"reason": f"Ollama connection error: {type(e).__name__}"}}
    except Exception as e_outer: # Catch any other unexpected errors during the process
        logger.error(f"MCP_SERVER: Unexpected error in query_llm_for_tool_choice: {e_outer}", exc_info=True)
        return {"tool_name": "no_tool", "arguments": {"reason": "Unexpected server error during tool choice."}}




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