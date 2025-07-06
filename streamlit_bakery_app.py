#!/usr/bin/env python3
"""
Streamlit Bakery Ecommerce Application
Integrates with MCP server for product data and AI-powered assistance.
"""

import streamlit as st
import json
from typing import List, Dict, Any, Optional
import asyncio
import os
import logging # Import logging
import atexit
import threading
import weakref
import time
import sys

# Configure logger FOR THE STREAMLIT APP
# Use this logger instance throughout streamlit_bakery_app.py
logging.basicConfig(level=logging.INFO, format='%(asctime)s - STREAMLIT_APP - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # This is the logger to use

# --- MCP Client Code (full version) ---
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_bakery_server.py") # Assumes server is in same dir

_background_loop = None
_background_thread = None
_clients = weakref.WeakSet()

def get_background_loop():
    global _background_loop, _background_thread
    if _background_thread is None or not _background_thread.is_alive():
        logger.info("Creating new background thread for MCP client")
        def run_background_loop():
            global _background_loop
            _background_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_background_loop)
            try:
                _background_loop.run_forever()
            except KeyboardInterrupt:
                logger.info("Background loop interrupted.")
            finally:
                if _background_loop.is_running(): # Ensure it is running before trying to close
                     _background_loop.call_soon_threadsafe(_background_loop.stop) # Stop it first
                _background_loop.close() # Then close
                logger.info("Background loop closed.")
        _background_thread = threading.Thread(target=run_background_loop, daemon=True)
        _background_thread.start()
        while _background_loop is None or not _background_loop.is_running():
            time.sleep(0.01)
    return _background_loop

class MCPError(Exception):
    def __init__(self, details: Dict[str, Any]):
        self.details = details
        super().__init__(details.get("message", "Unknown MCP error"))

class BackgroundMCPClient:
    def __init__(self, timeout=15.0):
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
        _clients.add(self)

    def _get_next_request_id(self) -> str:
        self._request_id_counter += 1
        return str(self._request_id_counter)

    async def _stdout_reader(self):
        logger.info("MCP Client: Stdout reader started.")
        try:
            while self._keep_alive and self.process and self.process.stdout and not self.process.stdout.at_eof():
                try:
                    line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)
                    if not line:
                        if self._keep_alive: logger.warning("MCP Client: Stdout EOF detected unexpectedly.")
                        break
                    line_str = line.decode('utf-8').strip()
                    if line_str:
                        logger.debug(f"MCP Client: Received raw: {line_str[:300]}") # Log snippet
                        try:
                            response = json.loads(line_str)
                            await self._handle_response(response)
                        except json.JSONDecodeError:
                            logger.error(f"MCP Client: Failed to decode JSON: {line_str}")
                        except Exception as e:
                            logger.error(f"MCP Client: Error processing message: {e}", exc_info=True)
                except asyncio.TimeoutError:
                    continue # Normal if no messages
        except asyncio.CancelledError:
            logger.info("MCP Client: Stdout reader cancelled.")
        except Exception as e:
            if self._keep_alive: logger.error(f"MCP Client: Stdout reader error: {e}", exc_info=True)
        finally:
            logger.info("MCP Client: Stdout reader finished.")

    async def _handle_response(self, response: Dict[str, Any]):
        request_id = response.get("id")
        if request_id is not None:
            request_id_str = str(request_id) # Ensure key is string
            future = self._pending_requests.pop(request_id_str, None)
            if future and not future.done():
                if "result" in response:
                    future.set_result(response["result"])
                elif "error" in response:
                    future.set_exception(MCPError(response["error"]))
                else:
                    future.set_exception(MCPError({"message": "Invalid response format", "code": -32000}))
            elif future and future.done():
                logger.warning(f"MCP Client: Received response for already completed/timed-out request {request_id_str}")
            elif not future:
                 logger.warning(f"MCP Client: Received response for unknown/timed-out id: {request_id_str}")
        else:
            method = response.get("method")
            if method: logger.debug(f"MCP Client: Received notification: {method}")

    async def _stderr_reader(self):
        logger.info("MCP Client: Stderr reader started.")
        try:
            while self._keep_alive and self.process and self.process.stderr and not self.process.stderr.at_eof():
                try:
                    line = await asyncio.wait_for(self.process.stderr.readline(), timeout=1.0)
                    if not line: break
                    logger.info(f"MCP SERVER LOG: {line.decode('utf-8').strip()}")
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("MCP Client: Stderr reader cancelled.")
        except Exception as e:
            if self._keep_alive: logger.error(f"MCP Client: Stderr reader error: {e}", exc_info=True)
        finally:
            logger.info("MCP Client: Stderr reader finished.")

    async def _connect_async(self) -> bool:
        if self.is_connected: return True
        try:
            if not os.path.exists(MCP_SERVER_SCRIPT):
                logger.error(f"MCP Server script not found: {MCP_SERVER_SCRIPT}")
                return False

            self._loop = asyncio.get_running_loop()
            logger.info(f"MCP Client: Starting MCP server process from: {MCP_SERVER_SCRIPT}")
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, MCP_SERVER_SCRIPT, # Use sys.executable
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await asyncio.sleep(0.5) 

            if self.process.returncode is not None:
                logger.error(f"MCP server failed to start. Return code: {self.process.returncode}")
                return False
            
            self._keep_alive = True
            self._reader_task = self._loop.create_task(self._stdout_reader())
            self._stderr_task = self._loop.create_task(self._stderr_reader())
            
            await asyncio.sleep(1.5) 
            
            request_id = self._get_next_request_id()
            future = self._loop.create_future()
            self._pending_requests[request_id] = future # Store with string ID
            
            init_params = {"processId": os.getpid(), "clientInfo": {"name": "StreamlitBakeryClient", "version": "1.0"}, "capabilities": {}, "trace": "off"}
            mcp_request = {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": init_params}
            request_json = json.dumps(mcp_request) + "\n"
            
            logger.info(f"MCP Client: Sending initialize request (ID: {request_id})...")
            if self.process.stdin:
                self.process.stdin.write(request_json.encode('utf-8'))
                await self.process.stdin.drain()
            else:
                logger.error("MCP Client: Stdin is not available for initialize request.")
                return False # Or raise an error
            
            init_response = await asyncio.wait_for(future, timeout=self.timeout)
            self.server_capabilities = init_response.get("capabilities")
            logger.info(f"MCP server initialized. Capabilities: {self.server_capabilities}")
            
            await self._send_notification("initialized", {})
            logger.info("MCP Client: Sent initialized notification.")
            
            self.is_connected = True
            logger.info("MCP Client: Connection established.")
            return True

        except asyncio.TimeoutError:
            logger.error(f"MCP Client: Initialize request timed out after {self.timeout}s.")
        except ConnectionRefusedError: # Should not happen with subprocess but good practice
            logger.error(f"MCP Client: Connection refused. Ensure server is running and accessible.")
        except Exception as e:
            logger.error(f"MCP Client: Failed to connect/initialize: {e}", exc_info=True)
        
        await self._disconnect_async(graceful_shutdown_timeout=2.0)
        return False

    def connect(self) -> bool:
        loop = get_background_loop()
        if not loop.is_running():
            logger.error("MCP Client: Background loop is not running. Cannot connect.")
            return False
        future_conn = asyncio.run_coroutine_threadsafe(self._connect_async(), loop)
        try:
            return future_conn.result(timeout=self.timeout + 10) 
        except Exception as e:
            logger.error(f"MCP Client: Connect future result error: {e}", exc_info=True)
            return False

    async def _send_notification(self, method: str, params: Dict[str, Any]):
        if not self.process or not self.process.stdin or self.process.stdin.is_closing():
            logger.warning(f"MCP Client: Cannot send notification {method}, stdin not available.")
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self.process.stdin.write((json.dumps(notification) + "\n").encode('utf-8'))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, AttributeError) as e:
            logger.error(f"MCP Client: Connection error sending notification {method}: {e}")
            await self._disconnect_async(graceful_shutdown_timeout=1.0)

    async def _send_request_and_wait_async(self, method: str, params: Dict[str, Any]) -> Any:
        if not self.is_connected or not self.process or not self.process.stdin or self.process.stdin.is_closing():
            logger.error(f"MCP Client: Not connected or stdin closed for method {method}.")
            raise MCPError({"message": "Not connected to server or stdin closed", "code": -32001})

        request_id = self._get_next_request_id()
        future = self._loop.create_future()
        self._pending_requests[request_id] = future # Store with string ID
        mcp_request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        
        logger.debug(f"MCP Client: Sending {method} (ID: {request_id}) params: {json.dumps(params)[:100]}...")
        try:
            self.process.stdin.write((json.dumps(mcp_request) + "\n").encode('utf-8'))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, AttributeError) as e:
            self._pending_requests.pop(request_id, None)
            if not future.done(): future.cancel()
            logger.error(f"MCP Client: Connection error sending request {method}: {e}")
            await self._disconnect_async(graceful_shutdown_timeout=1.0)
            raise MCPError({"message": f"Connection error: {e}", "code": -32002}) from e

        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None) 
            logger.error(f"MCP Client: Request {method} (ID: {request_id}) timed out after {self.timeout}s.")
            raise MCPError({"message": f"Request timed out: {method}", "code": -32003})
        except asyncio.CancelledError:
            logger.warning(f"MCP Client: Request {method} (ID: {request_id}) was cancelled.")
            raise MCPError({"message": f"Request cancelled, possibly due to connection loss: {method}", "code": -32004})

    def _send_request_and_wait(self, method: str, params: Dict[str, Any]) -> Any:
        if not self._loop or not self._loop.is_running():
            logger.error("MCP Client: Background loop not running for _send_request_and_wait.")
            raise MCPError({"message": "Client background loop not running", "code": -32001})
        
        future_req = asyncio.run_coroutine_threadsafe(self._send_request_and_wait_async(method, params), self._loop)
        try:
            return future_req.result(timeout=self.timeout + 5) 
        except Exception as e: 
            logger.error(f"MCP Client: Synchronous request {method} failed: {e}", exc_info=True)
            if isinstance(e, MCPError): raise
            raise MCPError({"message": f"Failed to execute {method}: {str(e)}", "code": -32000})

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.is_healthy():
            logger.error(f"MCP client not healthy. Cannot call tool: {tool_name}.")
            return {"error": f"MCP client not healthy. Cannot call tool: {tool_name}."}
        try:
            result = self._send_request_and_wait("tools/call", {"name": tool_name, "arguments": arguments})
            # Expect result to be like: {"content": [{"type": "text", "text": "{\"response_text\": \"...\"}"}]}
            # Or for older tools: {"content": [{"type": "text", "text": "[{...product...}]"}]}
            if result and "content" in result and result["content"] and isinstance(result["content"], list) and "text" in result["content"][0]:
                return json.loads(result["content"][0]["text"]) # Client expects the deserialized dict/list from "text"
            logger.warning(f"MCP Client: Unexpected tool response structure for {tool_name}: {result}")
            return {"error": "Malformed tool response"}
        except MCPError as e:
            logger.error(f"MCP Client: MCPError calling tool {tool_name}: {e.details}")
            return {"error": e.details.get("message", str(e))}
        except json.JSONDecodeError as e:
            logger.error(f"MCP Client: JSON decode error in tool response for {tool_name}: {e}. Raw text: {result.get('content',[{}])[0].get('text','') if result else 'N/A'}")
            return {"error": f"Tool response JSON decode error: {e}"}
        except Exception as e:
            logger.error(f"MCP Client: Generic error calling tool {tool_name}: {e}", exc_info=True)
            return {"error": str(e)}

    def read_resource(self, uri: str) -> Any:
        if not self.is_healthy():
            logger.error(f"MCP client not healthy. Cannot read resource: {uri}.")
            return {"error": f"MCP client not healthy. Cannot read resource: {uri}."}
        try:
            result = self._send_request_and_wait("resources/read", {"uri": uri})
            if result and "contents" in result and result["contents"] and isinstance(result["contents"], list) and "text" in result["contents"][0]:
                return json.loads(result["contents"][0]["text"]) # Client expects the deserialized dict/list
            logger.warning(f"MCP Client: Unexpected resource response structure for {uri}: {result}")
            return {"error": "Malformed resource response"}
        except MCPError as e:
            logger.error(f"MCP Client: MCPError reading resource {uri}: {e.details}")
            return {"error": e.details.get("message", str(e))}
        except json.JSONDecodeError as e:
            logger.error(f"MCP Client: JSON decode error in resource for {uri}: {e}. Raw text: {result.get('contents',[{}])[0].get('text','') if result else 'N/A'}")
            return {"error": f"Resource JSON decode error: {e}"}
        except Exception as e:
            logger.error(f"MCP Client: Generic error reading resource {uri}: {e}", exc_info=True)
            return {"error": str(e)}
            
    async def _disconnect_async(self, graceful_shutdown_timeout=5.0):
        logger.info("MCP Client: Disconnecting...")
        self._keep_alive = False
        
        if self.is_connected and self.process and self.process.stdin and not self.process.stdin.is_closing():
            try:
                # No shutdown request, just exit notification as per simple LSP
                await self._send_notification("exit", {})
                logger.info("MCP Client: Sent exit notification to server.")
            except Exception as e:
                logger.warning(f"MCP Client: Error during graceful shutdown notification: {e}")

        if self._reader_task and not self._reader_task.done(): self._reader_task.cancel()
        if self._stderr_task and not self._stderr_task.done(): self._stderr_task.cancel()

        try:
            await asyncio.gather(
                self._reader_task if self._reader_task else asyncio.sleep(0),
                self._stderr_task if self._stderr_task else asyncio.sleep(0),
                return_exceptions=True
            )
        except Exception as e:
            logger.warning(f"MCP Client: Error while waiting for reader tasks to cancel: {e}")

        if self.process:
            if self.process.stdin and not self.process.stdin.is_closing():
                try: self.process.stdin.close()
                except Exception: pass 
            
            if self.process.returncode is None:
                try:
                    logger.info(f"MCP Client: Terminating server process {self.process.pid}...")
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=graceful_shutdown_timeout)
                    logger.info(f"MCP Client: Server process {self.process.pid} terminated with code {self.process.returncode}.")
                except asyncio.TimeoutError:
                    logger.warning(f"MCP Client: Server process {self.process.pid} did not terminate gracefully, killing.")
                    self.process.kill()
                    await self.process.wait() # Ensure kill is processed
                    logger.info(f"MCP Client: Server process {self.process.pid} killed with code {self.process.returncode}.")
                except Exception as e:
                     logger.error(f"MCP Client: Error terminating/killing process {self.process.pid}: {e}", exc_info=True)
            self.process = None
        
        self.is_connected = False
        logger.info("MCP Client: Disconnected.")

    def disconnect(self):
        if self._loop and self._loop.is_running():
            future_disc = asyncio.run_coroutine_threadsafe(self._disconnect_async(), self._loop)
            try:
                future_disc.result(timeout=10.0) # Increased timeout
            except Exception as e:
                logger.error(f"MCP Client: Disconnect future result error: {e}", exc_info=True)
        else:
             if self.process and self.process.returncode is None:
                try: self.process.kill(); logger.info("Fallback: Killed MCP process directly.")
                except Exception as e_kill: logger.error(f"Fallback: Error killing process: {e_kill}")
        self.is_connected = False # Ensure this is set

    def is_healthy(self) -> bool:
        healthy = (self.is_connected and 
                   self.process is not None and self.process.returncode is None and
                   self._reader_task is not None and not self._reader_task.done() and
                   self._stderr_task is not None and not self._stderr_task.done())
        if not healthy:
            logger.debug(f"Health check: connected={self.is_connected}, process_exists={self.process is not None}, "
                        f"process_retcode={self.process.returncode if self.process else 'N/A'}, "
                        f"reader_ok={self._reader_task is not None and not self._reader_task.done() if self._reader_task else False}, "
                        f"stderr_ok={self._stderr_task is not None and not self._stderr_task.done() if self._stderr_task else False}")
        return healthy

def initialize_mcp_client() -> Optional[BackgroundMCPClient]:
    logger.info("Initializing MCP client...")
    client = BackgroundMCPClient() # Default timeout 15s
    if client.connect(): # connect has timeout of client.timeout + 10 = 25s
        logger.info("MCP client connected successfully.")
        return client
    logger.warning("MCP client connection failed.")
    client.disconnect() # Ensure cleanup if connect failed
    return None

def cleanup_clients():
    logger.info("Cleaning up MCP clients at exit...")
    # Create a copy of client references for iteration as disconnect might modify _clients
    current_clients = list(_clients)
    for client in current_clients: 
        if client: # Check if the object still exists
            try:
                logger.info(f"Disconnecting client: {client}")
                client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client {client}: {e}", exc_info=True)
    
    global _background_loop, _background_thread
    if _background_loop and _background_loop.is_running():
        logger.info("Stopping background event loop...")
        _background_loop.call_soon_threadsafe(_background_loop.stop)
        if _background_thread and _background_thread.is_alive():
            _background_thread.join(timeout=5.0) 
            if _background_thread.is_alive():
                logger.warning("Background thread did not stop in time.")
    logger.info("Cleanup finished.")

atexit.register(cleanup_clients)
# --- End MCP Client Code ---

# --- Mock data for Fallback ---
MOCK_PRODUCTS = [
    {"id": 1, "name": "Mock Cookies", "description": "Tasty mock cookies", "price": 10.99, "category": "cookies", "rating": 4.5, "stock_quantity": 10, "image_url": "🍪", "dietary_info": ["contains gluten"]},
    {"id": 2, "name": "Mock Bread", "description": "Fresh mock bread", "price": 5.99, "category": "bread", "rating": 4.7, "stock_quantity": 5, "image_url": "🍞", "dietary_info": ["vegan"]},
]
MOCK_CATEGORIES = ["cookies", "bread", "cakes"]


# --- UI Helper Functions ---
def display_product_card(item: Dict[str, Any], col_index: int):
    with st.container(border=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"<div style='font-size: 50px; text-align: center; padding-top: 10px;'>{item.get('image_url', '❓')}</div>", unsafe_allow_html=True)
        with col2:
            st.subheader(item.get('name', 'N/A'))
            st.caption(item.get('description', 'No description.'))
            st.write(f"**Category:** {item.get('category', 'N/A').title()}")
            st.write(f"**Price:** ${item.get('price', 0.0):.2f}")
            st.write(f"**Rating:** {'⭐' * int(item.get('rating', 0))} ({item.get('rating', 0.0):.1f}/5)")
            stock = item.get('stock_quantity', 0)
            if stock > 0: st.write(f"**Stock:** {stock} available")
            else: st.write(f"**Stock:** <span style='color:red;'>Out of stock</span>", unsafe_allow_html=True)
            dietary_info = item.get('dietary_info', [])
            if dietary_info:
                badges = " ".join([f"<span style='background-color: #e0e0e0; color: #333; padding: 3px 8px; border-radius: 12px; font-size: 12px; margin: 2px; display: inline-block;'>{info}</span>" for info in dietary_info])
                st.markdown(f"**Dietary:** {badges}", unsafe_allow_html=True)
        if stock > 0:
            if st.button("Add to Cart", key=f"add_{item.get('id', col_index)}_{col_index}", type="primary", use_container_width=True):
                add_to_cart(item)
        else:
            st.button("Out of Stock", key=f"add_{item.get('id', col_index)}_{col_index}", disabled=True, use_container_width=True)

def add_to_cart(item: Dict[str, Any]):
    cart_item = {'id': item.get('id'), 'name': item.get('name'), 'price': item.get('price'), 'image_url': item.get('image_url'), 'description': item.get('description')}
    st.session_state.cart.append(cart_item)
    st.toast(f"Added {item.get('name', 'Item')} to cart!", icon="🛒")

# --- MCP Interaction / AI Assistant Logic ---
def get_ai_assistant_response(user_input: str, client: Optional[BackgroundMCPClient], chat_history: list) -> str:
    if not client or not client.is_healthy():
        logger.warning("AI Assistant: MCP client not healthy or not available.")
        if 'hello' in user_input.lower() or 'hi' in user_input.lower():
            return "Hello! I'm in limited mode (MCP not connected). How can I help?"
        return "I'm having trouble connecting to my full capabilities right now (MCP server issue). Please try again later."
    try:
        tool_args = {"user_input": user_input, "chat_history": chat_history}
        assistant_response_payload = client.call_tool("assistant_chat", tool_args)
        if isinstance(assistant_response_payload, dict) and "response_text" in assistant_response_payload:
            return assistant_response_payload["response_text"]
        elif isinstance(assistant_response_payload, dict) and "error" in assistant_response_payload:
            logger.error(f"AI Assistant tool returned an error: {assistant_response_payload['error']}")
            return f"Sorry, I encountered an error: {assistant_response_payload['error']}"
        else:
            logger.error(f"Unexpected response structure from assistant_chat tool: {assistant_response_payload}")
            return "Sorry, I received an unexpected response from the AI assistant."
    except MCPError as e:
        logger.error(f"MCPError calling assistant_chat tool: {e.details}")
        return f"I couldn't reach my AI brain (MCP Error: {e.details.get('message', str(e))}). Please try again."
    except Exception as e:
        logger.error(f"Generic error in get_ai_assistant_response: {e}", exc_info=True)
        return f"An unexpected error occurred while trying to get a response: {str(e)}"

# --- Main Application ---
def main():
    st.set_page_config(page_title="Sweet Delights Bakery (MCP+LLM)", page_icon="🍰", layout="wide")

    if 'mcp_client' not in st.session_state: st.session_state.mcp_client = None
    if 'products_from_mcp' not in st.session_state: st.session_state.products_from_mcp = []
    if 'product_categories' not in st.session_state: st.session_state.product_categories = []
    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'chat_history' not in st.session_state: 
        st.session_state.chat_history = [{"role": "assistant", "content": "Hello! I'm your AI Bakery Assistant. Ask me anything!"}]
    if 'app_initialized' not in st.session_state: st.session_state.app_initialized = False
    if 'mcp_connection_status' not in st.session_state: st.session_state.mcp_connection_status = "🟡 Unknown"

    if not st.session_state.app_initialized:
        with st.spinner("🍰 Initializing Bakery Systems... Connecting to MCP Server..."):
            if st.session_state.mcp_client is None: # Initialize only if not already done
                client_instance = initialize_mcp_client()
                st.session_state.mcp_client = client_instance
            else: # Use existing client if already initialized (e.g. after a reconnect attempt)
                client_instance = st.session_state.mcp_client

            if client_instance and client_instance.is_healthy():
                st.session_state.mcp_connection_status = "🟢 Connected"
                logger.info("MCP client connected. Fetching initial data...")
                
                # --- DEBUGGING STEP: Comment out direct fetching, use mock data ---
                # logger.info("Attempting to fetch products_data via MCP...")
                # products_data = client_instance.read_resource("bakery://products/all") 
                # logger.info("Attempting to fetch categories_data via MCP...")
                # categories_data = client_instance.read_resource("bakery://products/categories")

                # if isinstance(products_data, list):
                #     st.session_state.products_from_mcp = products_data
                #     logger.info(f"Successfully fetched {len(products_data)} products.")
                # elif isinstance(products_data, dict) and "error" in products_data:
                #      logger.error(f"Error fetching products: {products_data['error']}")
                #      st.session_state.products_from_mcp = MOCK_PRODUCTS 
                #      st.session_state.mcp_connection_status += " (Product fetch error, using mock)"
                # else: 
                #     logger.warning(f"Unexpected product data format: {type(products_data)}. Using mock products.")
                #     st.session_state.products_from_mcp = MOCK_PRODUCTS
                #     st.session_state.mcp_connection_status += " (Product data format issue, using mock)"

                # if isinstance(categories_data, list):
                #     st.session_state.product_categories = categories_data
                #     logger.info(f"Successfully fetched {len(categories_data)} categories.")
                # else: 
                #     logger.warning(f"Unexpected categories data format or error: {categories_data}. Using mock categories.")
                #     st.session_state.product_categories = MOCK_CATEGORIES
                #     if isinstance(categories_data, dict) and "error" in categories_data:
                #         st.session_state.mcp_connection_status += f" (Category fetch error: {categories_data['error']}, using mock)"
                #     else:
                #         st.session_state.mcp_connection_status += " (Category data format issue, using mock)"
                # --- END OF DEBUGGING COMMENT OUT ---

                # --- ACTIVATE THIS FOR DEBUGGING ---
                st.session_state.products_from_mcp = MOCK_PRODUCTS
                st.session_state.product_categories = MOCK_CATEGORIES
                logger.info("DEBUGGING STEP: Using mock data for products and categories after connect attempt.")
                # --- END OF DEBUGGING ACTIVATION ---
            else:
                st.session_state.mcp_connection_status = "🔴 Disconnected (Using Mock Data)"
                logger.warning("MCP client not connected or unhealthy. Using mock data for products and categories.")
                st.session_state.products_from_mcp = MOCK_PRODUCTS
                st.session_state.product_categories = MOCK_CATEGORIES
            
            st.session_state.app_initialized = True
            if st.session_state.get('running_in_streamlit', True): # Avoid rerun if not in streamlit context
                st.rerun() 

    st.title("🍰 Sweet Delights Bakery")
    st.markdown(f"*Freshly baked goods, powered by MCP & LLM! Status: {st.session_state.mcp_connection_status}*")

    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", ["Browse Products", "AI Assistant", "Shopping Cart"], label_visibility="collapsed")

    if page == "Browse Products":
        st.header("Our Products")
        st.sidebar.markdown("---")
        st.sidebar.subheader("Filter Products")
        
        valid_categories = []
        if isinstance(st.session_state.get("product_categories"), list):
            valid_categories = [str(cat) for cat in st.session_state.product_categories if isinstance(cat, (str, int, float))]
        categories_options = ["All"] + sorted(list(set(valid_categories if valid_categories else MOCK_CATEGORIES)))
        category_filter = st.sidebar.selectbox("Category", categories_options)
        
        current_products = st.session_state.get("products_from_mcp", MOCK_PRODUCTS)
        if not isinstance(current_products, list): current_products = MOCK_PRODUCTS
        
        max_price_val = 30.0
        if current_products:
            prices = [float(p.get('price', 0.0)) for p in current_products if isinstance(p, dict) and isinstance(p.get('price'), (int, float))]
            if prices: max_price_val = float(max(prices)) if prices else 30.0
        
        price_filter_max_val = float(round(max_price_val + 5))
        price_filter = st.sidebar.slider("Max Price ($)", 0.0, price_filter_max_val, price_filter_max_val)
        
        all_dietary_infos = []
        if current_products:
             all_dietary_infos = sorted(list(set(info.lower() for item in current_products if isinstance(item, dict) for info in item.get('dietary_info', []) if isinstance(info, str))))
        dietary_filter_selected = st.sidebar.multiselect("Dietary Needs", all_dietary_infos)

        items_to_display = [item for item in current_products if isinstance(item, dict)] # Start with valid dicts
        if category_filter != "All":
            items_to_display = [item for item in items_to_display if item.get('category', '').lower() == category_filter.lower()]
        items_to_display = [item for item in items_to_display if float(item.get('price', 0.0)) <= price_filter]
        if dietary_filter_selected:
            for restriction in dietary_filter_selected:
                items_to_display = [item for item in items_to_display if restriction in [d.lower() for d in item.get('dietary_info', []) if isinstance(d, str)]]

        if items_to_display:
            num_cols = st.columns(3) # Use st.columns directly for fixed number
            for i, item in enumerate(items_to_display):
                with num_cols[i % 3]: # Cycle through columns
                    display_product_card(item, i)
        else:
            st.warning("No products match your filters. Try adjusting your criteria.")

    elif page == "AI Assistant":
        st.header("🤖 AI Bakery Assistant")
        st.markdown("Ask for recommendations, search, popular items, or just chat!")
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        if prompt := st.chat_input("Ask the AI Assistant..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("🧠 Thinking..."):
                    response = get_ai_assistant_response(prompt, st.session_state.mcp_client, st.session_state.chat_history)
                st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

        st.sidebar.markdown("---")
        st.sidebar.subheader("Quick Questions for AI:")
        sample_questions = ["Recommend something with chocolate", "Show popular items", "Search for vegan bread", "Details for product id 1", "What's your favorite cake?"]
        for q_idx, question in enumerate(sample_questions):
            if st.sidebar.button(question, key=f"sample_q_{q_idx}", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": question})
                with st.spinner("🧠 Thinking..."):
                    response = get_ai_assistant_response(question, st.session_state.mcp_client, st.session_state.chat_history)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.rerun()

    elif page == "Shopping Cart":
        st.header("🛒 Shopping Cart")
        if st.session_state.cart:
            total = 0.0
            for i, cart_item_dict in enumerate(st.session_state.cart):
                if isinstance(cart_item_dict, dict):
                    with st.container(border=True):
                        col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
                        with col1: st.markdown(f"<div style='font-size: 30px; text-align:center; padding-top:10px;'>{cart_item_dict.get('image_url','❓')}</div>", unsafe_allow_html=True)
                        with col2:
                            st.subheader(cart_item_dict.get('name', 'N/A'))
                            st.caption(cart_item_dict.get('description', '')[:60] + "...")
                        with col3: st.markdown(f"<div style='text-align: right; padding-top:20px; font-weight:bold;'>${cart_item_dict.get('price', 0.0):.2f}</div>", unsafe_allow_html=True)
                        with col4:
                            st.write("") 
                            if st.button("Remove", key=f"remove_{cart_item_dict.get('id', i)}_{i}", use_container_width=True):
                                st.session_state.cart.pop(i)
                                st.rerun()
                    total += cart_item_dict.get('price', 0.0)
            st.markdown("---")
            st.subheader(f"Total: ${total:.2f}")
            if st.button("Proceed to Checkout", type="primary", use_container_width=True):
                st.success("Thank you for your order! (Demo)")
                st.balloons()
                st.session_state.cart = []
                st.rerun()
        else:
            st.info("Your cart is empty. Browse our products to add items!")

    st.sidebar.markdown("---")
    st.sidebar.info("**Sweet Delights Bakery (MCP+LLM)**\n\n📍 123 Baker Street\n\n📞 (555) MCP-CAKE")
    if st.sidebar.button("🔄 Reconnect MCP", use_container_width=True):
        if st.session_state.mcp_client:
            logger.info("User triggered MCP reconnect: Disconnecting existing client.")
            st.session_state.mcp_client.disconnect()
        st.session_state.mcp_client = None # Clear client
        st.session_state.app_initialized = False # Trigger re-initialization
        logger.info("User triggered MCP reconnect: Rerunning app for re-initialization.")
        st.rerun()

if __name__ == "__main__":
    st.session_state['running_in_streamlit'] = True # Simple flag for conditional rerun
    logger.info("Starting Streamlit Bakery App with MCP+LLM Integration...")
    main()