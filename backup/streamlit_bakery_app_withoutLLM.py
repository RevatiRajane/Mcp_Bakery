#!/usr/bin/env python3
"""
READERS FIX - This prevents the readers from being cancelled
Save this as "streamlit_bakery_app_readers_fixed.py"
"""

import streamlit as st
import json
from typing import List, Dict, Any, Optional
import asyncio
import os
import logging
import atexit
import threading
import weakref

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - STREAMLIT_APP - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock data for fallback
MOCK_PRODUCTS = [
    {
        "id": 1, "name": "Classic Chocolate Chip Cookies", "description": "Soft and chewy cookies loaded with premium chocolate chips",
        "price": 12.99, "category": "cookies", "rating": 4.8, "stock_quantity": 25, "image_url": "🍪",
        "dietary_info": ["contains gluten", "contains dairy"]
    },
    {
        "id": 2, "name": "Fresh Sourdough Bread", "description": "Artisan sourdough with crispy crust and tangy flavor",
        "price": 8.50, "category": "bread", "rating": 4.9, "stock_quantity": 15, "image_url": "🍞",
        "dietary_info": ["vegan", "contains gluten"]
    },
    {
        "id": 3, "name": "Red Velvet Cupcakes", "description": "Moist red velvet cupcakes with cream cheese frosting",
        "price": 18.99, "category": "cupcakes", "rating": 4.7, "stock_quantity": 20, "image_url": "🧁",
        "dietary_info": ["contains gluten", "contains dairy"]
    },
    {
        "id": 4, "name": "Vegan Blueberry Muffins", "description": "Fluffy plant-based muffins bursting with fresh blueberries",
        "price": 15.99, "category": "muffins", "rating": 4.6, "stock_quantity": 18, "image_url": "🧁",
        "dietary_info": ["vegan", "contains gluten"]
    },
    {
        "id": 5, "name": "Gluten-Free Almond Croissants", "description": "Buttery, flaky croissants filled with almond cream",
        "price": 22.99, "category": "pastries", "rating": 4.5, "stock_quantity": 12, "image_url": "🥐",
        "dietary_info": ["gluten-free", "contains dairy", "contains nuts"]
    }
]

MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_bakery_server.py")

# Global background loop for managing the MCP client
_background_loop = None
_background_thread = None
_clients = weakref.WeakSet()

def get_background_loop():
    """Get or create the background event loop"""
    global _background_loop, _background_thread
    
    if _background_thread is None or not _background_thread.is_alive():
        logger.info("Creating new background thread for MCP client")
        
        def run_background_loop():
            global _background_loop
            _background_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_background_loop)
            _background_loop.run_forever()
        
        _background_thread = threading.Thread(target=run_background_loop, daemon=True)
        _background_thread.start()
        
        # Wait for loop to be ready
        while _background_loop is None:
            asyncio.sleep(0.1)
    
    return _background_loop

class MCPError(Exception):
    def __init__(self, details: Dict[str, Any]):
        self.details = details
        super().__init__(details.get("message", "Unknown MCP error"))

class BackgroundMCPClient:
    """MCP Client that runs in a background thread to prevent cancellation"""
    
    def __init__(self, timeout=10.0):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_connected = False
        self.server_capabilities: Optional[Dict[str, Any]] = None
        self._request_id_counter = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self.timeout = timeout
        self._keep_alive = True
        self._loop = None
        
        # Register this client
        _clients.add(self)

    def _get_next_request_id(self) -> str:
        self._request_id_counter += 1
        return str(self._request_id_counter)

    async def _stdout_reader(self):
        logger.info("MCP Client: Stdout reader started in background thread")
        while self._keep_alive and self.process and self.process.stdout and not self.process.stdout.at_eof():
            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)
                if not line:
                    if self._keep_alive:
                        logger.warning("MCP Client: Stdout EOF detected")
                    break
                line_str = line.decode('utf-8').strip()
                logger.debug(f"MCP Client: Received raw: {line_str}")
                if line_str:
                    try:
                        response = json.loads(line_str)
                        await self._handle_response(response)
                    except json.JSONDecodeError:
                        logger.error(f"MCP Client: Failed to decode JSON: {line_str}")
                    except Exception as e:
                        logger.error(f"MCP Client: Error processing message: {e}")
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("MCP Client: Stdout reader cancelled.")
                break
            except Exception as e:
                if self._keep_alive:
                    logger.error(f"MCP Client: Stdout reader error: {e}")
                break
        logger.info("MCP Client: Stdout reader finished.")

    async def _handle_response(self, response: Dict[str, Any]):
        request_id = response.get("id")
        
        if request_id is not None:
            request_id_str = str(request_id)
            if request_id_str in self._pending_requests:
                future = self._pending_requests.pop(request_id_str)
                if "result" in response:
                    logger.debug(f"MCP Client: Response received for request {request_id_str}")
                    future.set_result(response["result"])
                elif "error" in response:
                    logger.error(f"MCP Client: Error response for request {request_id_str}: {response['error']}")
                    future.set_exception(MCPError(response["error"]))
                else:
                    future.set_exception(MCPError({"message": "Invalid response format", "code": -32000}))
            else:
                logger.warning(f"MCP Client: Received response for unknown id: {request_id_str}")
        else:
            method = response.get("method")
            if method:
                logger.debug(f"MCP Client: Received notification: {method}")

    async def _stderr_reader(self):
        logger.info("MCP Client: Stderr reader started in background thread")
        while self._keep_alive and self.process and self.process.stderr and not self.process.stderr.at_eof():
            try:
                line = await asyncio.wait_for(self.process.stderr.readline(), timeout=1.0)
                if not line:
                    break
                logger.info(f"MCP SERVER LOG: {line.decode('utf-8').strip()}")
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("MCP Client: Stderr reader cancelled.")
                break
            except Exception as e:
                if self._keep_alive:
                    logger.error(f"MCP Client: Stderr reader error: {e}")
                break
        logger.info("MCP Client: Stderr reader finished.")

    async def _connect_async(self) -> bool:
        """Internal async connect method"""
        if self.is_connected:
            return True
        try:
            if not os.path.exists(MCP_SERVER_SCRIPT):
                logger.error(f"MCP Server script not found at: {MCP_SERVER_SCRIPT}")
                return False

            logger.info("Starting MCP server process...")
            self.process = await asyncio.create_subprocess_exec(
                "python3", MCP_SERVER_SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if self.process.returncode is not None:
                logger.error(f"MCP server failed to start. Return code: {self.process.returncode}")
                return False

            # Store the loop reference to prevent task cancellation
            self._loop = asyncio.get_running_loop()
            
            # Start readers and keep strong references
            self._keep_alive = True
            self._reader_task = self._loop.create_task(self._stdout_reader())
            self._stderr_task = self._loop.create_task(self._stderr_reader())
            
            logger.info("MCP Client: Waiting for server to start...")
            await asyncio.sleep(2.0)
            
            # Initialize
            request_id = self._get_next_request_id()
            future = self._loop.create_future()
            self._pending_requests[request_id] = future
            
            logger.info(f"MCP Client: Sending initialize request with ID {request_id}...")
            
            init_params = {
                "processId": os.getpid(),
                "clientInfo": {"name": "StreamlitBakeryGPTClient", "version": "0.1.0"},
                "rootUri": None,
                "capabilities": {},
                "trace": "off",
                "protocolVersion": "1.0"
            }
            
            mcp_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": init_params
            }
            request_json = json.dumps(mcp_request) + "\n"
            
            try:
                self.process.stdin.write(request_json.encode('utf-8'))
                await self.process.stdin.drain()
                logger.info(f"MCP Client: Initialize request sent, waiting for response...")
                
                init_response = await asyncio.wait_for(future, timeout=self.timeout)
                self.server_capabilities = init_response.get("capabilities")
                logger.info(f"MCP server initialized successfully. Capabilities: {self.server_capabilities}")
                
                # Send initialized notification
                await asyncio.sleep(0.2)
                await self._send_notification("notifications/initialized", {})
                logger.info("MCP Client: Sent initialized notification")
                
                await asyncio.sleep(0.5)
                
                self.is_connected = True
                logger.info("MCP Client: Connection established and ready for requests")
                
                # Verify readers are still running
                if self._reader_task.done() or self._stderr_task.done():
                    logger.error("MCP Client: Readers terminated unexpectedly!")
                    return False
                else:
                    logger.info("MCP Client: Readers confirmed running")
                
                return True
                
            except asyncio.TimeoutError:
                self._pending_requests.pop(request_id, None)
                logger.error(f"MCP Client: Initialize request timed out")
                await self._disconnect_async()
                return False
            except Exception as e:
                self._pending_requests.pop(request_id, None)
                logger.error(f"MCP Client: Initialize request failed: {e}")
                await self._disconnect_async()
                return False

        except Exception as e:
            logger.error(f"Failed to start or initialize MCP server: {e}", exc_info=True)
            if self.process:
                await self._disconnect_async()
            return False

    def connect(self) -> bool:
        """Synchronous connect method"""
        loop = get_background_loop()
        future = asyncio.run_coroutine_threadsafe(self._connect_async(), loop)
        return future.result(timeout=30)

    async def _send_notification(self, method: str, params: Dict[str, Any]):
        if not self.process or not self.process.stdin:
            raise MCPError({"message": "Not connected to server", "code": -32001})

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        notification_json = json.dumps(notification) + "\n"
        
        try:
            self.process.stdin.write(notification_json.encode('utf-8'))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            raise MCPError({"message": f"Connection error: {e}", "code": -32002}) from e

    async def _send_request_and_wait_async(self, method: str, params: Dict[str, Any]) -> Any:
        if not self.process or not self.process.stdin:
            raise MCPError({"message": "Not connected to server", "code": -32001})

        request_id = self._get_next_request_id()
        future = self._loop.create_future()
        self._pending_requests[request_id] = future

        mcp_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        request_json = json.dumps(mcp_request) + "\n"
        
        logger.debug(f"MCP Client: Sending {method} request (ID: {request_id})")
        try:
            self.process.stdin.write(request_json.encode('utf-8'))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            self._pending_requests.pop(request_id, None)
            raise MCPError({"message": f"Connection error: {e}", "code": -32002}) from e

        try:
            result = await asyncio.wait_for(future, timeout=self.timeout)
            logger.debug(f"MCP Client: Successfully received result for {method}")
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            logger.error(f"MCP Client: Request {method} timed out")
            raise MCPError({"message": f"Request timed out: {method}", "code": -32003})
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise

    def _send_request_and_wait(self, method: str, params: Dict[str, Any]) -> Any:
        """Synchronous wrapper for async requests"""
        if not self._loop:
            raise MCPError({"message": "Client not connected", "code": -32001})
        
        future = asyncio.run_coroutine_threadsafe(
            self._send_request_and_wait_async(method, params), 
            self._loop
        )
        return future.result(timeout=self.timeout + 5)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.is_connected:
            logger.warning(f"MCP Client: Not connected. Using mock response for tool: {tool_name}")
            return self._get_mock_response(tool_name, arguments)
        
        try:
            params = {"name": tool_name, "arguments": arguments}
            result = self._send_request_and_wait("tools/call", params)
            
            if result and "content" in result and isinstance(result["content"], list) and len(result["content"]) > 0:
                text_content = result["content"][0]
                if text_content.get("type") == "text" and "text" in text_content:
                    try:
                        return json.loads(text_content["text"])
                    except json.JSONDecodeError as e:
                        logger.error(f"MCP Client: Failed to parse JSON from tools/call: {e}")
                        return {"error": "Malformed tool response content"}
            return {"error": "Unexpected tool response structure"}
        except Exception as e:
            logger.error(f"MCP Client: Error calling tool {tool_name}: {e}")
            return {"error": str(e)}

    def read_resource(self, uri: str) -> Any:
        if not self.is_connected:
            if uri == "bakery://products/all":
                return MOCK_PRODUCTS
            return []
        
        try:
            params = {"uri": uri}
            result = self._send_request_and_wait("resources/read", params)
            if result and "contents" in result and isinstance(result["contents"], list) and len(result["contents"]) > 0:
                text_content = result["contents"][0]
                if text_content.get("type") == "text" and "text" in text_content:
                    try:
                        return json.loads(text_content["text"])
                    except json.JSONDecodeError as e:
                        logger.error(f"MCP Client: Failed to parse JSON from resource: {e}")
                        return {"error": "Malformed resource content"}
            return {"error": "Unexpected resource response structure"}
        except Exception as e:
            logger.error(f"MCP Client: Error reading resource {uri}: {e}")
            return {"error": str(e)}

    def list_tools(self) -> Any:
        if not self.is_connected:
            return {"error": "Not connected to MCP server."}
        try:
            result = self._send_request_and_wait("tools/list", {})
            return result.get("tools", [])
        except Exception as e:
            return {"error": f"Failed to list tools: {e}"}

    def list_resources(self) -> Any:
        if not self.is_connected:
            return {"error": "Not connected to MCP server."}
        try:
            result = self._send_request_and_wait("resources/list", {})
            return result.get("resources", [])
        except Exception as e:
            return {"error": f"Failed to list resources: {e}"}

    def _get_mock_response(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "get_product_recommendations":
            prefs = arguments.get("preferences", {})
            filtered_products = [p for p in MOCK_PRODUCTS if self._check_prefs(p, prefs)]
            return filtered_products[:3] if filtered_products else sorted(MOCK_PRODUCTS, key=lambda x: x["rating"], reverse=True)[:3]
        elif tool_name == "get_popular_products":
            limit = arguments.get("limit", 5)
            return sorted(MOCK_PRODUCTS, key=lambda x: x["rating"], reverse=True)[:limit]
        elif tool_name == "search_products":
            query = arguments.get("query", "").lower()
            return [p for p in MOCK_PRODUCTS if query in p["name"].lower() or query in p["description"].lower()]
        elif tool_name == "get_product_details":
            product_id = arguments.get("product_id")
            for product in MOCK_PRODUCTS:
                if product["id"] == product_id: 
                    return product
            return {"error": "Product not found (mock)"}
        return {"error": f"Unknown tool (mock): {tool_name}"}

    def _check_prefs(self, product: Dict, prefs: Dict) -> bool:
        if "dietary_restrictions" in prefs and prefs["dietary_restrictions"]:
            if not any(r in product.get("dietary_info", []) for r in prefs["dietary_restrictions"]):
                return False
        if "category" in prefs and prefs["category"] and product["category"] != prefs["category"]:
            return False
        if "max_price" in prefs and prefs["max_price"] is not None and product["price"] > prefs["max_price"]:
            return False
        return True

    async def _disconnect_async(self):
        logger.info("MCP Client: Disconnecting...")
        self._keep_alive = False
        self.is_connected = False

        # Cancel tasks
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()

        # Close process
        if self.process:
            if self.process.stdin and not self.process.stdin.is_closing():
                try:
                    self.process.stdin.close()
                except:
                    pass

            if self.process.returncode is None:
                try:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            self.process = None

    def disconnect(self):
        if self._loop:
            future = asyncio.run_coroutine_threadsafe(self._disconnect_async(), self._loop)
            future.result(timeout=10)

    def is_healthy(self) -> bool:
        return (self.is_connected and 
                self.process is not None and 
                self.process.returncode is None and
                self._reader_task is not None and 
                not self._reader_task.done() and
                self._stderr_task is not None and 
                not self._stderr_task.done())

def initialize_mcp_client() -> BackgroundMCPClient:
    logger.info("Initializing background MCP client...")
    client = BackgroundMCPClient()
    success = client.connect()
    
    if success:
        logger.info("MCP client connected successfully to the server.")
    else:
        logger.warning("MCP client connection failed. Will use mock data as fallback.")
    return client

def get_chatbot_response(user_input: str, client: BackgroundMCPClient) -> str:
    user_input_lower = user_input.lower()

    if not client.is_connected:
        if 'hello' in user_input_lower or 'hi' in user_input_lower:
            return "Hello! I'm in limited mode. Ask about 'popular items' for a demo."
        if 'popular' in user_input_lower:
            mock_popular = client._get_mock_response("get_popular_products", {"limit": 3})
            return format_items(mock_popular, "Here are some popular items (demo data):\n\n")
        return "I'm having trouble connecting to my brain right now. Please try again later."

    def format_items(items_data: Any, prefix: str) -> str:
        if isinstance(items_data, dict) and "error" in items_data:
            return f"Sorry, I encountered an error: {items_data['error']}"
        if not items_data or not isinstance(items_data, list):
            return "I couldn't find any matching items right now."
        
        response_str = prefix
        for i, item in enumerate(items_data[:3], 1):
            response_str += f"{i}. **{item.get('name', 'N/A')}** {item.get('image_url', '')} - ${item.get('price', 0.0):.2f}\n"
            desc = item.get('description', 'No description.')
            response_str += f"   {desc[:80]}...\n"
            rating = item.get('rating', 0)
            response_str += f"   Rating: {'⭐' * int(rating)} ({rating}/5)\n\n"
        return response_str

    if any(word in user_input_lower for word in ['recommend', 'suggestion']):
        preferences = {}
        if 'vegan' in user_input_lower:
            preferences.setdefault('dietary_restrictions', []).append('vegan')
        if 'gluten' in user_input_lower:
            preferences.setdefault('dietary_restrictions', []).append('gluten-free')
        
        all_categories = ["cookies", "bread", "cakes", "muffins", "pastries"]
        found_category = next((cat for cat in all_categories if cat in user_input_lower), None)
        if found_category:
            preferences['category'] = found_category
        
        if not preferences:
            recommendations = client.call_tool("get_popular_products", {"limit": 3})
            return format_items(recommendations, "Here are some popular items:\n\n")

        recommendations = client.call_tool("get_product_recommendations", {"preferences": preferences})
        return format_items(recommendations, "Based on your preferences:\n\n")

    elif any(word in user_input_lower for word in ['popular', 'bestseller', 'best']):
        popular_items = client.call_tool("get_popular_products", {"limit": 3})
        return format_items(popular_items, "Here are our most popular items:\n\n")

    elif any(word in user_input_lower for word in ['search', 'find']):
        search_terms = user_input_lower.replace('search for ', '').replace('search ', '').replace('find ', '').strip()
        if search_terms:
            search_results = client.call_tool("search_products", {"query": search_terms})
            return format_items(search_results, f"I found these items matching '{search_terms}':\n\n")
        else:
            return "What would you like me to search for?"

    elif 'hello' in user_input_lower or 'hi' in user_input_lower:
        return "Hello! Welcome to our AI Bakery! 🍰 I can help find recommendations, search for items, or show popular products. What can I do for you?"
    else:
        return "I'm here to help! You can ask me for:\n- Recommendations\n- Popular items\n- Search for specific items\n\nHow can I help?"

def main():
    st.set_page_config(page_title="🍰 Bakery GPT - WORKING!", layout="wide", page_icon="🍰")

    # Initialize session state
    if 'mcp_client' not in st.session_state:
        st.session_state.mcp_client = None
    if 'products_from_mcp' not in st.session_state:
        st.session_state.products_from_mcp = []
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'app_initialized' not in st.session_state:
        st.session_state.app_initialized = False

    if not st.session_state.app_initialized:
        with st.spinner("🔄 Connecting to Bakery Brain (MCP Server)..."):
            try:
                client_instance = initialize_mcp_client()
                st.session_state.mcp_client = client_instance
                st.session_state.app_initialized = True

                if client_instance and client_instance.is_connected:
                    st.success("✅ Successfully connected to Bakery Brain! 🧠")
                    
                    try:
                        products_data = client_instance.read_resource("bakery://products/all")
                        if isinstance(products_data, list) and len(products_data) > 0:
                            st.session_state.products_from_mcp = products_data
                            st.info(f"📊 Loaded {len(products_data)} products from MCP server!")
                        else:
                            st.warning("Using demo data - server responded but no products found")
                            st.session_state.products_from_mcp = MOCK_PRODUCTS
                    except Exception as e:
                        st.warning(f"Using demo data - error fetching products: {e}")
                        st.session_state.products_from_mcp = MOCK_PRODUCTS
                else:
                    st.warning("⚠️ Could not connect to MCP Server. Using demo mode 📚")
                    st.session_state.products_from_mcp = MOCK_PRODUCTS
            except Exception as e:
                st.error(f"❌ Initialization failed: {e}")
                logger.error(f"App initialization error: {e}", exc_info=True)
                st.session_state.products_from_mcp = MOCK_PRODUCTS

    # Header with status
    st.title("🍰 AI Bakery Assistant - READERS FIXED!")
    
    # Connection status
    connection_healthy = False
    if st.session_state.mcp_client:
        connection_healthy = st.session_state.mcp_client.is_healthy()

    if connection_healthy:
        st.success("🟢 **Status:** Connected to Live MCP Server (Readers Running)")
    elif st.session_state.mcp_client and st.session_state.mcp_client.is_connected:
        st.warning("🟡 **Status:** Connected but readers may have issues")
    else:
        st.error("🔴 **Status:** Demo Mode - MCP Server not connected")

    # Products display
    st.subheader(f"Our Delicious Offerings ({len(st.session_state.products_from_mcp)} items)")
    if st.session_state.products_from_mcp:
        cols = st.columns(3)
        for i, product in enumerate(st.session_state.products_from_mcp[:6]):
            with cols[i % 3]:
                st.markdown(f"### {product.get('name', 'N/A')} {product.get('image_url', '')}")
                st.caption(f"{product.get('description', 'No description.')}")
                st.markdown(f"**${product.get('price', 0.0):.2f}** | ⭐ {product.get('rating', 0.0)}/5")

    # Test section
    st.divider()
    st.subheader("🧪 Live Connection Tests")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔥 Test Popular", type="primary"):
            if st.session_state.mcp_client and connection_healthy:
                try:
                    with st.spinner("Testing..."):
                        result = st.session_state.mcp_client.call_tool("get_popular_products", {"limit": 2})
                        if isinstance(result, list) and len(result) > 0:
                            st.success(f"✅ SUCCESS! Got {len(result)} products!")
                            for item in result:
                                st.write(f"• {item.get('name', 'Unknown')} - ${item.get('price', 0):.2f}")
                        else:
                            st.error(f"❌ Unexpected result: {result}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
            else:
                st.warning("MCP not healthy or not connected")
    
    with col2:
        if st.button("🔍 Test Search"):
            if st.session_state.mcp_client and connection_healthy:
                try:
                    with st.spinner("Searching..."):
                        result = st.session_state.mcp_client.call_tool("search_products", {"query": "chocolate"})
                        if isinstance(result, list):
                            st.success(f"✅ SUCCESS! Found {len(result)} items!")
                            for item in result[:2]:
                                st.write(f"• {item.get('name', 'Unknown')}")
                        else:
                            st.error(f"❌ Search failed: {result}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
            else:
                st.warning("MCP not healthy")
    
    with col3:
        if st.button("📊 Test Resources"):
            if st.session_state.mcp_client and connection_healthy:
                try:
                    with st.spinner("Testing..."):
                        result = st.session_state.mcp_client.list_resources()
                        if isinstance(result, list):
                            st.success(f"✅ SUCCESS! Found {len(result)} resources!")
                            for res in result:
                                st.write(f"• {res.get('name', 'Unknown')}")
                        else:
                            st.error(f"❌ Failed: {result}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
            else:
                st.warning("MCP not healthy")
    
    with col4:
        if st.button("🔄 Reconnect"):
            if st.session_state.mcp_client:
                try:
                    st.session_state.mcp_client.disconnect()
                except:
                    pass
            st.session_state.app_initialized = False
            st.session_state.mcp_client = None
            st.rerun()

    # Chat interface
    st.divider()
    st.subheader("💬 Chat with our AI Assistant")
    
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask for recommendations, search, or say hi..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("🧠 Thinking...")
            
            if st.session_state.mcp_client:
                try:
                    response = get_chatbot_response(prompt, st.session_state.mcp_client)
                except Exception as e:
                    logger.error(f"Error getting chatbot response: {e}", exc_info=True)
                    response = f"I'm sorry, I encountered an error: {str(e)}"
            else:
                response = "Error: MCP Client not available."

            message_placeholder.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

def cleanup_clients():
    """Clean up all MCP clients"""
    global _background_loop, _background_thread
    logger.info("Cleaning up MCP clients...")
    
    for client in list(_clients):
        try:
            client.disconnect()
        except:
            pass
    
    if _background_loop and _background_loop.is_running():
        _background_loop.call_soon_threadsafe(_background_loop.stop)

if __name__ == "__main__":
    logger.info("Starting Streamlit Bakery App (Readers Fixed Version)...")
    atexit.register(cleanup_clients)
    
    try:
        main()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        st.error(f"Critical error: {e}")

# Requirements: pip install streamlit mcp-sdk