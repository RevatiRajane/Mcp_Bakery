#!/usr/bin/env python3
"""
MCP Bakery Server
Responds to JSON-RPC requests from a client (e.g., Streamlit Bakery App)
to provide product information and recommendations.
"""

import sys
import json
import logging
import os

# --- Server Configuration ---
# Configure logger to output to stderr, so stdout can be used for JSON-RPC
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - MCP_SERVER - %(levelname)s - %(message)s',
    stream=sys.stderr  # Important: logs to stderr
)
logger = logging.getLogger(__name__)

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
        "price": 7.00, "category": "Pastries", "rating": 4.7, "stock_quantity": 0, # Example of out of stock
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
        "image_url": "🍫", "dietary_info": ["gluten-free", "contains dairy", "vegetarian"] # Note: can be made vegan if dairy-free
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
    """Sends a JSON-RPC response to stdout."""
    message = {"jsonrpc": "2.0", "id": response_id}
    if result is not None:
        message["result"] = result
    if error is not None:
        message["error"] = error
    
    json_message = json.dumps(message)
    logger.debug(f"Sending response: {json_message}")
    print(json_message, flush=True) # Ensure it's sent immediately

def create_error_response(code, message, data=None):
    """Creates a JSON-RPC error object."""
    error_obj = {"code": code, "message": message}
    if data:
        error_obj["data"] = data
    return error_obj

def format_tool_call_response_content(data_payload):
    """
    Formats the data payload as expected by the client for tool calls.
    The client expects: result["content"][0]["text"] to be a JSON string.
    """
    return {"content": [{"type": "text", "text": json.dumps(data_payload)}]}

def format_resource_read_response_content(data_payload):
    """
    Formats the data payload as expected by the client for resource reads.
    The client expects: result["contents"][0]["text"] to be a JSON string.
    """
    return {"contents": [{"type": "text", "text": json.dumps(data_payload)}]}


# --- Tool Implementations ---
def get_popular_products(arguments):
    limit = arguments.get("limit", 3)
    # Sort by rating (desc) then by stock (desc, to prioritize in-stock)
    sorted_products = sorted(PRODUCTS_DATA, key=lambda p: (p.get("rating", 0), p.get("stock_quantity", 0)), reverse=True)
    return sorted_products[:limit]

def get_product_recommendations(arguments):
    preferences = arguments.get("preferences", {})
    dietary_restrictions = [r.lower() for r in preferences.get("dietary_restrictions", [])]
    category_pref = preferences.get("category", "").lower()

    recommended = []
    for product in PRODUCTS_DATA:
        if product.get("stock_quantity", 0) == 0: # Skip out of stock items for recommendations
            continue

        matches_dietary = True
        if dietary_restrictions:
            product_diet_info = [info.lower() for info in product.get("dietary_info", [])]
            # Check if all specified restrictions are met
            # This logic assumes dietary_info lists what it *contains* or properties like "vegan" / "gluten-free"
            # For "vegan", we need "vegan" to be in product_diet_info
            # For "gluten-free", we need "gluten-free" to be in product_diet_info
            # If a restriction is "no dairy", we'd need to ensure "contains dairy" is NOT in product_diet_info
            # The current client sends "vegan" or "gluten-free" as positive requirements.
            for restriction in dietary_restrictions:
                if restriction not in product_diet_info:
                    matches_dietary = False
                    break
        
        matches_category = True
        if category_pref:
            if product.get("category", "").lower() != category_pref:
                matches_category = False
        
        if matches_dietary and matches_category:
            recommended.append(product)
            
    return recommended[:5] # Limit recommendations

def search_products(arguments):
    query = arguments.get("query", "").lower()
    if not query:
        return []
    
    results = []
    for product in PRODUCTS_DATA:
        if query in product.get("name", "").lower() or \
           query in product.get("description", "").lower() or \
           query in product.get("category", "").lower() or \
           any(query in di.lower() for di in product.get("dietary_info", [])):
            results.append(product)
    return results

def get_product_details(arguments):
    product_id = arguments.get("product_id")
    if product_id is None:
        return create_error_response(-32602, "Missing product_id parameter")

    try:
        product_id = int(product_id)
    except ValueError:
        return create_error_response(-32602, "Invalid product_id format, must be an integer")

    for product in PRODUCTS_DATA:
        if product.get("id") == product_id:
            return product
    return {"error": "Product not found", "id": product_id} # Return as data payload, client expects this for tools

TOOLS = {
    "get_popular_products": get_popular_products,
    "get_product_recommendations": get_product_recommendations,
    "search_products": search_products,
    "get_product_details": get_product_details,
}

# --- Resource Implementations ---
def read_products_all(uri_params=None):
    return PRODUCTS_DATA

def read_products_categories(uri_params=None):
    return CATEGORIES_DATA

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

    logger.info(f"Received method: {method}, params: {json.dumps(params)[:200]}")

    if method == "initialize":
        # Client sends: {"processId": ..., "clientInfo": ..., "capabilities": {}, "trace": "off"}
        # Server responds with its capabilities
        server_capabilities = {
            "textDocumentSync": { # Example capability, adjust as needed for MCP
                "openClose": True,
                "change": 1 # Full sync
            },
            "workspace": {
                "workspaceFolders": {"supported": True}
            },
            "experimental": {
                "bakeryTools": True # Custom capability
            }
        }
        send_response(req_id, result={"capabilities": server_capabilities})

    elif method == "initialized": # This is a notification
        logger.info("Client initialized.")
        # No response needed for notifications

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_arguments = params.get("arguments", {})
        if tool_name in TOOLS:
            try:
                tool_result = TOOLS[tool_name](tool_arguments)
                if isinstance(tool_result, dict) and "code" in tool_result and "message" in tool_result: # It's an error object from tool
                    send_response(req_id, error=tool_result)
                else: # It's actual data
                    formatted_result = format_tool_call_response_content(tool_result)
                    send_response(req_id, result=formatted_result)
            except Exception as e:
                logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                send_response(req_id, error=create_error_response(-32000, f"Server error executing tool {tool_name}: {str(e)}"))
        else:
            send_response(req_id, error=create_error_response(-32601, f"Tool not found: {tool_name}"))
    
    elif method == "resources/read":
        uri = params.get("uri")
        # Potentially parse URI for params, e.g., bakery://products/item?id=1
        # For now, direct match on URI string
        if uri in RESOURCES:
            try:
                resource_data = RESOURCES[uri]() # Add uri_params if needed
                formatted_data = format_resource_read_response_content(resource_data)
                send_response(req_id, result=formatted_data)
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}", exc_info=True)
                send_response(req_id, error=create_error_response(-32000, f"Server error reading resource {uri}: {str(e)}"))
        else:
            send_response(req_id, error=create_error_response(-32601, f"Resource not found: {uri}"))

    elif method == "shutdown": # Optional: Client might send this before exit
        logger.info("Shutdown request received. Preparing to exit.")
        # Perform any cleanup if necessary
        if req_id: send_response(req_id, result=None) # Acknowledge shutdown
        # The server will wait for 'exit' notification to actually terminate

    elif method == "exit": # Notification
        logger.info("Exit notification received. Terminating server.")
        sys.exit(0) # Graceful exit

    else:
        if req_id: send_response(req_id, error=create_error_response(-32601, f"Method not found: {method}"))
        logger.warning(f"Unknown method received: {method}")


# --- Main Server Loop ---
def main():
    logger.info("MCP Bakery Server started. Listening on stdin...")
    logger.info(f"PID: {os.getpid()}")
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                logger.info("Stdin closed. Exiting.")
                break # EOF

            line = line.strip()
            if not line:
                continue # Skip empty lines

            logger.debug(f"Received raw line: {line}")
            try:
                request_obj = json.loads(line)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON: {line}")
                # Cannot send error if we don't have an ID.
                # If it was a malformed request that had an ID, we could try to parse ID.
                # For now, just log and continue.
                continue
            
            handle_request(request_obj)

    except KeyboardInterrupt:
        logger.info("Server interrupted by KeyboardInterrupt. Exiting.")
    except Exception as e:
        logger.error(f"Unhandled exception in main loop: {e}", exc_info=True)
    finally:
        logger.info("MCP Bakery Server shutting down.")

if __name__ == "__main__":
    main()