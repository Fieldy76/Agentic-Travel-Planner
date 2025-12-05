/**
 * ================================================================================
 * AGENTIC TRAVEL PLANNER - Main Application JavaScript
 * ================================================================================
 * 
 * This file contains all the client-side JavaScript for the Agentic Travel Planner.
 * It handles user interactions, API communication, real-time streaming, and UI updates.
 * 
 * Architecture Overview:
 * ─────────────────────
 * 
 *   ┌─────────────────┐         ┌──────────────────┐
 *   │   User Input    │────────▶│  Form Submission │
 *   └─────────────────┘         └────────┬─────────┘
 *                                        │
 *                                        ▼
 *   ┌─────────────────────────────────────────────────┐
 *   │              Fetch API (POST /api/chat)         │
 *   │      Sends: {message, file} as FormData         │
 *   └────────────────────┬────────────────────────────┘
 *                        │
 *                        ▼
 *   ┌─────────────────────────────────────────────────┐
 *   │            NDJSON Streaming Response            │
 *   │  Events: message, tool_call, tool_result, error │
 *   └────────────────────┬────────────────────────────┘
 *                        │
 *          ┌─────────────┼─────────────┐
 *          ▼             ▼             ▼
 *   ┌──────────┐  ┌───────────┐  ┌───────────┐
 *   │ Message  │  │ Tool Call │  │ Tool      │
 *   │ Display  │  │ Display   │  │ Result    │
 *   └──────────┘  └───────────┘  └───────────┘
 *                        │
 *                        ▼
 *   ┌─────────────────────────────────────────────────┐
 *   │           LocalStorage Persistence              │
 *   │     Conversation history saved automatically    │
 *   └─────────────────────────────────────────────────┘
 * 
 * Key Features:
 * ─────────────
 * 1. NDJSON Streaming - Real-time response parsing
 * 2. Conversation History - LocalStorage persistence
 * 3. File Uploads - Multipart form data support
 * 4. Modal System - Confirmation, input, search dialogs
 * 5. Tool Visualization - Icons and status for agent tools
 * 6. Toast Notifications - User feedback messages
 * 
 * Event Types (from server):
 * ─────────────────────────
 * - message: Text content from the assistant
 * - tool_call: Agent is invoking a tool
 * - tool_result: Tool execution completed
 * - error: Something went wrong
 * 
 * LocalStorage Keys:
 * ─────────────────
 * - travelSearchHistory: Array of conversation objects
 * 
 * Author: Agentic Travel Planner Team
 * ================================================================================
 */

// =============================================================================
// INITIALIZATION
// =============================================================================
// Wait for DOM to be fully loaded before initializing
document.addEventListener('DOMContentLoaded', () => {

    // =========================================================================
    // DOM ELEMENT REFERENCES
    // =========================================================================
    // Cache references to frequently used DOM elements for performance

    // Core chat elements
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatContainer = document.getElementById('chat-container');
    const sendBtn = document.getElementById('send-btn');

    // Status indicator elements
    const statusIndicator = document.getElementById('status-indicator');
    const statusDot = statusIndicator.querySelector('.status-dot');
    const statusText = statusIndicator.querySelector('.status-text');

    // Sidebar elements
    const historyToggle = document.getElementById('history-toggle');
    const historySidebar = document.getElementById('history-sidebar');
    const historyList = document.getElementById('history-list');
    const clearHistoryBtn = document.getElementById('clear-history');
    const newChatBtn = document.getElementById('new-chat-btn');

    // Search modal elements
    const searchBtn = document.getElementById('search-btn');
    const searchModal = document.getElementById('search-modal');
    const modalSearchInput = document.getElementById('modal-search-input');
    const searchResultsList = document.getElementById('search-results-list');

    // =========================================================================
    // APPLICATION STATE
    // =========================================================================
    // Global state variables for the application

    let isProcessing = false;               // True when waiting for agent response
    let searchHistory = loadSearchHistory(); // Array of conversation objects
    let currentConversationId = null;        // ID of the active conversation
    let conversationMessages = [];           // Messages in current conversation

    // =========================================================================
    // SEARCH MODAL LOGIC
    // =========================================================================
    // Handles the full-screen search overlay for finding conversations

    if (searchBtn && searchModal) {
        // Open search modal when search button is clicked
        searchBtn.addEventListener('click', () => {
            openSearchModal();
        });

        // Close modal when clicking outside the content area
        searchModal.addEventListener('click', (e) => {
            if (e.target === searchModal) {
                closeSearchModal();
            }
        });

        // Filter results as user types
        modalSearchInput.addEventListener('input', (e) => {
            renderSearchResults(e.target.value);
        });
    }

    /**
     * Opens the search modal with animation.
     * Resets the search input and shows all conversations initially.
     */
    function openSearchModal() {
        if (!searchModal) return;
        searchModal.classList.remove('hidden');
        // Use requestAnimationFrame for smooth CSS transition
        requestAnimationFrame(() => searchModal.classList.add('active'));

        modalSearchInput.value = '';
        modalSearchInput.focus();
        renderSearchResults(); // Show all initially
    }

    /**
     * Closes the search modal with fade-out animation.
     * Uses setTimeout to wait for animation before hiding.
     */
    function closeSearchModal() {
        if (!searchModal) return;
        searchModal.classList.remove('active');
        setTimeout(() => searchModal.classList.add('hidden'), 200);
    }

    /**
     * Renders filtered search results based on query string.
     * Filters conversation titles case-insensitively.
     * 
     * @param {string} query - Search query to filter by (default: empty = show all)
     */
    function renderSearchResults(query = '') {
        if (!searchResultsList) return;
        searchResultsList.innerHTML = '';

        // Filter conversations by title
        const filteredHistory = searchHistory.filter(c =>
            c.title.toLowerCase().includes(query.toLowerCase())
        );

        // Show "no results" message if nothing matches
        if (filteredHistory.length === 0) {
            searchResultsList.innerHTML = '<div style="padding: 1rem; color: #888;">No results found</div>';
            return;
        }

        // Create a clickable item for each matching conversation
        filteredHistory.forEach(conversation => {
            const item = document.createElement('div');
            item.className = 'search-result-item';

            // Format timestamp as "Today", "Yesterday", or "Dec 3"
            const timeStr = formatSimpleDate(conversation.timestamp);

            item.innerHTML = `
                <div class="search-result-title">${escapeHtml(conversation.title)}</div>
                <div class="search-result-date">${timeStr}</div>
            `;

            // Load conversation when clicked
            item.addEventListener('click', () => {
                loadConversation(conversation.id);
                closeSearchModal();
                // On mobile, also collapse sidebar
                if (window.innerWidth < 768) {
                    historySidebar.classList.add('collapsed');
                }
            });

            searchResultsList.appendChild(item);
        });
    }

    /**
     * Formats a timestamp into a human-readable relative date.
     * Returns "Today", "Yesterday", or short date format.
     * 
     * @param {string} isoString - ISO 8601 date string
     * @returns {string} Formatted date string
     */
    function formatSimpleDate(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (date.toDateString() === now.toDateString()) {
            return 'Today';
        }
        if (diffDays === 1) {
            return 'Yesterday';
        }
        // Return short date like "Dec 3"
        return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }

    // =========================================================================
    // NEW CHAT BUTTON HANDLER
    // =========================================================================

    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            startNewConversation();
            // On mobile, collapse sidebar after starting new chat
            if (window.innerWidth < 768) {
                historySidebar.classList.add('collapsed');
            }
        });
    }

    // Initialize history display on page load
    renderHistory();

    // =========================================================================
    // FILE ATTACHMENT HANDLING
    // =========================================================================

    const fileInput = document.getElementById('file-input');
    let selectedFile = null;  // Currently selected file (if any)

    // =========================================================================
    // SIDEBAR TOGGLE
    // =========================================================================

    historyToggle.addEventListener('click', () => {
        historySidebar.classList.toggle('collapsed');
    });

    // =========================================================================
    // ATTACHMENT MENU
    // =========================================================================
    // Pop-up menu for file upload options

    const menuBtn = document.getElementById('attach-menu-btn');
    const menu = document.getElementById('attachment-menu');

    // Toggle menu visibility on button click
    menuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('active');
    });

    // Close menu when clicking anywhere else
    document.addEventListener('click', (e) => {
        if (!menu.contains(e.target) && !menuBtn.contains(e.target)) {
            menu.classList.remove('active');
        }
    });

    // Close menu when file input is clicked
    fileInput.addEventListener('click', () => {
        menu.classList.remove('active');
    });

    /**
     * Creates and displays a file pill showing the selected file.
     * The pill includes a remove button to deselect the file.
     * 
     * @param {File} file - The selected file object
     */
    function updateFilePill(file) {
        // Remove any existing pill first
        let existingPill = document.querySelector('.file-pill');
        if (existingPill) existingPill.remove();

        // Create new pill element
        const pill = document.createElement('div');
        pill.className = 'file-pill';
        pill.innerHTML = `
            <span class="file-name">${file.name}</span>
            <button type="button" class="remove-file">×</button>
        `;

        // Insert before the text input
        chatForm.insertBefore(pill, userInput);

        // Handle remove button click
        pill.querySelector('.remove-file').addEventListener('click', () => {
            selectedFile = null;
            if (fileInput) fileInput.value = '';
            pill.remove();
        });

        userInput.focus();
    }

    // Handle file selection
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            selectedFile = e.target.files[0];
            updateFilePill(selectedFile);
        }
    });

    // =========================================================================
    // CLEAR HISTORY BUTTON
    // =========================================================================

    clearHistoryBtn.addEventListener('click', () => {
        // Show confirmation modal before clearing
        showConfirmModal(
            'Clear History',
            'Are you sure you want to clear all search history?',
            () => {
                // User confirmed - clear everything
                searchHistory = [];
                saveSearchHistory();
                renderHistory();
                startNewConversation();
            }
        );
    });

    // =========================================================================
    // CHAT FORM SUBMISSION
    // =========================================================================
    // Main handler for sending messages to the agent

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        let message = userInput.value.trim();

        let fileToSend = null;

        // Handle file attachment
        if (selectedFile) {
            fileToSend = selectedFile;

            // Reset file state
            selectedFile = null;
            fileInput.value = '';
            const pill = document.querySelector('.file-pill');
            if (pill) pill.remove();
        }

        // Don't submit empty messages (unless there's a file)
        if ((!message && !fileToSend) || isProcessing) return;

        // Switch UI to "active conversation" mode (hides welcome message)
        chatContainer.classList.add('has-messages');

        // Create new conversation if this is the first message
        if (currentConversationId === null) {
            currentConversationId = Date.now().toString();
            addConversationToHistory(message);
        }

        // Display user message
        appendMessage('user', message);
        saveCurrentConversation();

        // Clear input and show processing state
        userInput.value = '';
        setProcessing(true);

        try {
            // ─────────────────────────────────────────────────────────────────
            // API REQUEST
            // ─────────────────────────────────────────────────────────────────
            // Send message to the backend as multipart form data

            const formData = new FormData();
            formData.append('message', message);
            if (fileToSend) {
                formData.append('file', fileToSend);
            }

            const response = await fetch('/api/chat', {
                method: 'POST',
                // Note: Don't set Content-Type header - browser sets it with boundary
                body: formData
            });

            // ─────────────────────────────────────────────────────────────────
            // STREAMING RESPONSE PARSING (NDJSON)
            // ─────────────────────────────────────────────────────────────────
            // The server sends newline-delimited JSON (NDJSON) events.
            // We read the stream incrementally and parse each complete line.

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';  // Accumulates partial data between reads

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                // Decode chunk and add to buffer
                buffer += decoder.decode(value, { stream: true });

                // Split by newlines to get complete events
                const lines = buffer.split('\n');

                // Keep the last (potentially incomplete) line in the buffer
                buffer = lines.pop();

                // Process each complete line
                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const event = JSON.parse(line);
                            handleEvent(event);
                        } catch (e) {
                            console.error('Error parsing JSON:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error:', error);
            appendMessage('assistant', 'Sorry, something went wrong. Please try again.');
        } finally {
            // Always reset processing state
            setProcessing(false);
            saveCurrentConversation();
        }
    });

    // =========================================================================
    // EVENT HANDLING
    // =========================================================================
    // Processes events received from the streaming API

    /**
     * Handles an event from the NDJSON stream.
     * Routes to appropriate handler based on event type.
     * 
     * @param {Object} event - Parsed event object from stream
     * @param {string} event.type - Event type (message, tool_call, tool_result, error)
     */
    function handleEvent(event) {
        switch (event.type) {
            case 'message':
                // Filter out raw tool output messages
                if (!event.content.includes('```tool_outputs')) {
                    appendMessage('assistant', event.content);
                }
                break;
            case 'tool_call':
                // Show tool call card with "running" status
                appendToolCall(event.name, event.arguments);
                break;
            case 'tool_result':
                // Update the tool card to show completion
                updateToolResult(event.name, event.content, event.is_error);
                break;
            case 'error':
                appendMessage('assistant', `Error: ${event.content}`);
                break;
        }
    }

    // =========================================================================
    // MESSAGE DISPLAY
    // =========================================================================

    /**
     * Appends a message bubble to the chat container.
     * Handles markdown link rendering and HTML escaping.
     * 
     * @param {string} role - 'user' or 'assistant'
     * @param {string} content - Message text content
     */
    function appendMessage(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Process content: escape HTML, convert newlines, render links
        let formattedContent = escapeHtml(content)
            .replace(/\n/g, '<br>')
            // Convert markdown links [text](url) to HTML anchors
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

        contentDiv.innerHTML = formattedContent;

        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);
        scrollToBottom();

        // Update internal state for persistence
        conversationMessages.push({ role, content });
    }

    // =========================================================================
    // TOOL CALL DISPLAY
    // =========================================================================

    /**
     * Displays a tool call card showing the agent is using a tool.
     * Shows tool icon, name, arguments, and "running" status.
     * 
     * @param {string} name - Tool name (e.g., 'search_flights')
     * @param {Object} args - Tool arguments
     */
    function appendToolCall(name, args) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call';
        toolDiv.id = `tool-${Date.now()}`;

        // Get user-friendly display information
        const displayInfo = getToolDisplayInfo(name, args);

        toolDiv.innerHTML = `
            <div class="tool-icon">
                ${displayInfo.icon}
            </div>
            <div class="tool-details">
                <div class="tool-name">${displayInfo.title}</div>
                <div class="tool-args">${displayInfo.description}</div>
            </div>
            <div class="tool-status running">${displayInfo.runningText}</div>
        `;

        chatContainer.appendChild(toolDiv);
        scrollToBottom();

        // Store reference to update status later
        window.lastToolDiv = toolDiv;

        // Add to conversation state
        conversationMessages.push({
            role: 'tool_call_ui',
            name,
            args,
            displayInfo
        });
    }

    /**
     * Returns user-friendly display information for a tool.
     * Maps tool names to icons, titles, and descriptions.
     * 
     * @param {string} name - Tool name
     * @param {Object} args - Tool arguments
     * @returns {Object} Display info with icon, title, description, runningText
     */
    function getToolDisplayInfo(name, args) {
        switch (name) {
            case 'search_flights':
                return {
                    title: 'Flight Search',
                    description: `${args.origin || '?'} → ${args.destination || '?'} on ${args.date || '?'}`,
                    runningText: 'Searching...',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"></path></svg>'
                };
            case 'get_forecast':
                return {
                    title: 'Weather Forecast',
                    description: `${args.location || '?'} on ${args.date || '?'}`,
                    runningText: 'Checking weather...',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path><circle cx="12" cy="12" r="5"></circle></svg>'
                };
            case 'rent_car':
                return {
                    title: 'Car Rental',
                    description: `${args.location || '?'} from ${args.start_date || '?'} to ${args.end_date || '?'}`,
                    runningText: 'Searching cars...',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"></path><circle cx="7" cy="17" r="2"></circle><path d="M9 17h6"></path><circle cx="17" cy="17" r="2"></circle></svg>'
                };
            case 'book_flight':
                return {
                    title: 'Flight Booking',
                    description: `Booking for ${args.passenger_name || '?'}`,
                    runningText: 'Booking...',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"></path></svg>'
                };
            case 'process_payment':
                return {
                    title: 'Payment Processing',
                    description: `${args.amount || '?'} ${args.currency || ''}`,
                    runningText: 'Processing...',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>'
                };
            default:
                return {
                    title: formatToolName(name),
                    description: JSON.stringify(args),
                    runningText: 'Running...',
                    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
                };
        }
    }

    /**
     * Updates the last tool call card with completion status.
     * Changes "running" to "Completed" or "Error".
     * 
     * @param {string} name - Tool name (for logging)
     * @param {string} content - Tool result content (unused in UI)
     * @param {boolean} isError - Whether the tool execution failed
     */
    function updateToolResult(name, content, isError) {
        if (window.lastToolDiv) {
            const statusDiv = window.lastToolDiv.querySelector('.tool-status');
            statusDiv.classList.remove('running');

            if (isError) {
                statusDiv.textContent = 'Error';
                statusDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                statusDiv.style.color = '#ef4444';
            } else {
                statusDiv.textContent = 'Completed';
                statusDiv.style.backgroundColor = 'rgba(34, 197, 94, 0.1)';
                statusDiv.style.color = '#22c55e';
            }
            window.lastToolDiv = null;
        }
    }

    /**
     * Converts snake_case tool name to Title Case.
     * Example: "search_flights" → "Search Flights"
     * 
     * @param {string} name - Tool name in snake_case
     * @returns {string} Formatted tool name
     */
    function formatToolName(name) {
        return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    }

    /**
     * Scrolls the chat container to show the latest message.
     */
    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // =========================================================================
    // PROCESSING STATE
    // =========================================================================

    /**
     * Updates the UI to reflect processing state.
     * Shows/hides the "Thinking" bubble and disables input.
     * 
     * @param {boolean} processing - True when waiting for response
     */
    function setProcessing(processing) {
        isProcessing = processing;
        userInput.disabled = processing;
        sendBtn.disabled = processing;

        if (processing) {
            // Show "busy" status
            statusDot.classList.add('busy');
            statusText.textContent = 'Thinking...';

            // Add animated "Thinking" bubble
            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'message assistant thinking-bubble';
            thinkingDiv.id = 'thinking-indicator';
            thinkingDiv.innerHTML = `
                <div class="message-content">
                    <div class="thinking-wrapper">
                        <span class="thinking-text">Thinking</span>
                        <div class="typing-indicator">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                </div>
            `;
            chatContainer.appendChild(thinkingDiv);
            scrollToBottom();
        } else {
            // Restore "ready" status
            statusDot.classList.remove('busy');
            statusText.textContent = 'Ready';
            userInput.focus();

            // Remove "Thinking" bubble
            const thinkingDiv = document.getElementById('thinking-indicator');
            if (thinkingDiv) {
                thinkingDiv.remove();
            }
        }
    }

    // =========================================================================
    // LOCALSTORAGE PERSISTENCE
    // =========================================================================
    // Functions for saving/loading conversation history

    /**
     * Loads search history from localStorage.
     * Returns empty array if nothing saved or on error.
     * 
     * @returns {Array} Array of conversation objects
     */
    function loadSearchHistory() {
        try {
            const saved = localStorage.getItem('travelSearchHistory');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            console.error('Error loading search history:', e);
            return [];
        }
    }

    /**
     * Saves current search history to localStorage.
     */
    function saveSearchHistory() {
        try {
            localStorage.setItem('travelSearchHistory', JSON.stringify(searchHistory));
        } catch (e) {
            console.error('Error saving search history:', e);
        }
    }

    /**
     * Updates the current conversation's messages in history.
     */
    function saveCurrentConversation() {
        if (!currentConversationId) return;

        const index = searchHistory.findIndex(c => c.id === currentConversationId);
        if (index !== -1) {
            searchHistory[index].messages = conversationMessages;
            saveSearchHistory();
        }
    }

    /**
     * Creates a new conversation entry in history.
     * 
     * @param {string} firstMessage - The first message (used as title)
     */
    function addConversationToHistory(firstMessage) {
        const conversationItem = {
            id: currentConversationId,
            // Truncate long messages for title
            title: firstMessage.length > 50 ? firstMessage.substring(0, 50) + '...' : firstMessage,
            timestamp: new Date().toISOString(),
            messages: []
        };

        // Add to beginning (most recent first)
        searchHistory.unshift(conversationItem);

        // Limit history to 50 conversations
        if (searchHistory.length > 50) {
            searchHistory = searchHistory.slice(0, 50);
        }

        saveSearchHistory();
        renderHistory();
    }

    // =========================================================================
    // CONVERSATION MANAGEMENT
    // =========================================================================

    /**
     * Starts a fresh conversation.
     * Clears the chat and resets state.
     */
    function startNewConversation() {
        // Reset chat container with welcome message
        chatContainer.innerHTML = `
            <div class="welcome-message">
                <div class="hero-text">
                    <span class="gradient-text">Hello, Traveler</span>
                </div>
                <p class="subtitle">How can I help you explore the world today?</p>
            </div>
        `;
        chatContainer.classList.remove('has-messages');
        currentConversationId = null;
        conversationMessages = [];
        userInput.value = '';
        userInput.focus();

        // Deselect any active history item
        document.querySelectorAll('.history-item').forEach(item => item.classList.remove('active'));
    }

    /**
     * Loads a conversation from history.
     * Replays all messages to rebuild the UI.
     * 
     * @param {string} id - Conversation ID to load
     */
    function loadConversation(id) {
        const conversation = searchHistory.find(c => c.id === id);
        if (!conversation) return;

        currentConversationId = id;
        conversationMessages = conversation.messages || [];

        // Reset chat with welcome message (hidden when has-messages)
        chatContainer.innerHTML = `
            <div class="welcome-message">
                <div class="hero-text">
                    <span class="gradient-text">Hello, Traveler</span>
                </div>
                <p class="subtitle">How can I help you explore the world today?</p>
            </div>
        `;

        if (conversationMessages.length > 0) {
            chatContainer.classList.add('has-messages');
        } else {
            chatContainer.classList.remove('has-messages');
        }

        // Replay messages to rebuild UI
        conversationMessages.forEach(msg => {
            if (msg.role === 'tool_call_ui') {
                // Reconstruct tool call display
                const toolDiv = document.createElement('div');
                toolDiv.className = 'tool-call';

                const displayInfo = msg.displayInfo || getToolDisplayInfo(msg.name, msg.args);

                toolDiv.innerHTML = `
                    <div class="tool-icon">
                        ${displayInfo.icon}
                    </div>
                    <div class="tool-details">
                        <div class="tool-name">${displayInfo.title}</div>
                        <div class="tool-args">${displayInfo.description}</div>
                    </div>
                    <div class="tool-status completed" style="background-color: rgba(34, 197, 94, 0.1); color: #22c55e;">Completed</div>
                `;
                chatContainer.appendChild(toolDiv);
            } else {
                appendMessage(msg.role, msg.content);
            }
        });

        // Reset state to loaded messages (appendMessage adds duplicates)
        conversationMessages = conversation.messages || [];

        scrollToBottom();
        renderHistory();
    }

    /**
     * Deletes a conversation after confirmation.
     * 
     * @param {string} id - Conversation ID to delete
     * @param {Event} event - Click event (for stopPropagation)
     */
    function deleteConversation(id, event) {
        event.stopPropagation();

        showConfirmModal(
            'Delete Conversation',
            'Are you sure you want to delete this conversation?',
            () => {
                searchHistory = searchHistory.filter(c => c.id !== id);
                saveSearchHistory();
                renderHistory();

                // If deleting current conversation, start new
                if (currentConversationId === id) {
                    startNewConversation();
                }
            }
        );
    }

    /**
     * Renames a conversation.
     * 
     * @param {string} id - Conversation ID
     * @param {string} newTitle - New title to set
     */
    function renameConversation(id, newTitle) {
        const conversation = searchHistory.find(c => c.id === id);
        if (conversation) {
            conversation.title = newTitle;
            saveSearchHistory();
            renderHistory();
        }
    }

    /**
     * Toggles pin status of a conversation.
     * Pinned conversations appear at the top.
     * 
     * @param {string} id - Conversation ID
     */
    function togglePinConversation(id) {
        const conversation = searchHistory.find(c => c.id === id);
        if (conversation) {
            conversation.pinned = !conversation.pinned;
            // Re-sort: pinned first, then by timestamp
            searchHistory.sort((a, b) => {
                if (a.pinned && !b.pinned) return -1;
                if (!a.pinned && b.pinned) return 1;
                return new Date(b.timestamp) - new Date(a.timestamp);
            });
            saveSearchHistory();
            renderHistory();
        }
    }

    // =========================================================================
    // HISTORY SIDEBAR RENDERING
    // =========================================================================

    /**
     * Renders the conversation history list in the sidebar.
     * Creates clickable items with dropdown menus.
     */
    function renderHistory() {
        if (searchHistory.length === 0) {
            historyList.innerHTML = '<div class="history-empty">No search history yet</div>';
            return;
        }

        historyList.innerHTML = '';
        searchHistory.forEach((conversation) => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';

            // Highlight active conversation
            if (conversation.id === currentConversationId) {
                historyItem.classList.add('active');
            }

            // Show pin indicator
            if (conversation.pinned) {
                historyItem.classList.add('pinned');
            }

            historyItem.innerHTML = `
                <div class="history-item-content">
                    <div class="history-item-text">${escapeHtml(conversation.title)}</div>
                    <div class="history-item-time">${formatTimestamp(conversation.timestamp)}</div>
                </div>
                <div class="history-menu-wrapper">
                    <button class="history-menu-btn" title="Options">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                            <circle cx="12" cy="5" r="2"/>
                            <circle cx="12" cy="12" r="2"/>
                            <circle cx="12" cy="19" r="2"/>
                        </svg>
                    </button>
                    <div class="history-dropdown hidden">
                        <button class="dropdown-item share-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                            </svg>
                            Share conversation
                        </button>
                        <button class="dropdown-item pin-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="12" y1="17" x2="12" y2="22"/>
                                <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/>
                            </svg>
                            ${conversation.pinned ? 'Unpin' : 'Pin'}
                        </button>
                        <button class="dropdown-item rename-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                            </svg>
                            Rename
                        </button>
                        <button class="dropdown-item delete-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                            Delete
                        </button>
                    </div>
                </div>
            `;

            // Click item content to load conversation
            historyItem.querySelector('.history-item-content').addEventListener('click', () => {
                loadConversation(conversation.id);
            });

            // 3-dot menu toggle
            const menuBtn = historyItem.querySelector('.history-menu-btn');
            const dropdown = historyItem.querySelector('.history-dropdown');
            menuBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                // Close all other dropdowns
                document.querySelectorAll('.history-dropdown').forEach(d => d.classList.add('hidden'));

                // Position dropdown
                const rect = menuBtn.getBoundingClientRect();
                dropdown.style.top = `${rect.bottom + 4}px`;
                dropdown.style.left = `${rect.left - 150}px`;

                dropdown.classList.toggle('hidden');
            });

            // Share button handler
            historyItem.querySelector('.share-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.classList.add('hidden');
                const shareText = `Check out my conversation: ${conversation.title}`;
                if (navigator.share) {
                    navigator.share({ title: conversation.title, text: shareText });
                } else {
                    navigator.clipboard.writeText(shareText);
                    showToast('Copied to clipboard!');
                }
            });

            // Pin button handler
            historyItem.querySelector('.pin-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.classList.add('hidden');
                togglePinConversation(conversation.id);
            });

            // Rename button handler
            historyItem.querySelector('.rename-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.classList.add('hidden');
                showInputModal('Rename Conversation', 'Enter new title', conversation.title, (newTitle) => {
                    renameConversation(conversation.id, newTitle);
                });
            });

            // Delete button handler
            historyItem.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.classList.add('hidden');
                deleteConversation(conversation.id, e);
            });

            historyList.appendChild(historyItem);
        });

        // Close dropdowns when clicking outside
        document.addEventListener('click', () => {
            document.querySelectorAll('.history-dropdown').forEach(d => d.classList.add('hidden'));
        });
    }

    /**
     * Formats a timestamp into a human-readable relative time.
     * Examples: "Just now", "5m ago", "2h ago", "3d ago", or full date
     * 
     * @param {string} isoString - ISO 8601 date string
     * @returns {string} Formatted time string
     */
    function formatTimestamp(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString();
    }

    // =========================================================================
    // MODAL DIALOGS
    // =========================================================================

    /**
     * Shows a confirmation modal with yes/no buttons.
     * 
     * @param {string} title - Modal title
     * @param {string} message - Confirmation message
     * @param {Function} onConfirm - Callback when user confirms
     */
    function showConfirmModal(title, message, onConfirm) {
        const modal = document.getElementById('confirmation-modal');
        const modalTitle = document.getElementById('modal-title');
        const modalMessage = document.getElementById('modal-message');
        const confirmBtn = document.getElementById('modal-confirm');
        const cancelBtn = document.getElementById('modal-cancel');

        if (!modal) return;

        modalTitle.textContent = title;
        modalMessage.textContent = message;

        // Show modal with animation
        modal.classList.remove('hidden');
        requestAnimationFrame(() => {
            modal.classList.add('active');
        });

        // Cleanup function to remove event listeners
        const cleanup = () => {
            confirmBtn.removeEventListener('click', handleConfirm);
            cancelBtn.removeEventListener('click', handleCancel);
        };

        // Close modal with animation
        const closeModal = () => {
            modal.classList.remove('active');
            setTimeout(() => {
                modal.classList.add('hidden');
            }, 300);
            cleanup();
        };

        // Handler functions
        const handleConfirm = () => {
            onConfirm();
            closeModal();
        };

        const handleCancel = () => {
            closeModal();
        };

        // Attach handlers (using onclick to avoid listener buildup)
        confirmBtn.onclick = handleConfirm;
        cancelBtn.onclick = handleCancel;
    }

    /**
     * Shows an input modal for text entry.
     * 
     * @param {string} title - Modal title
     * @param {string} placeholder - Input placeholder text
     * @param {string} defaultValue - Initial input value
     * @param {Function} onConfirm - Callback with entered value
     */
    function showInputModal(title, placeholder, defaultValue, onConfirm) {
        const modal = document.getElementById('input-modal');
        const modalTitle = document.getElementById('input-modal-title');
        const inputField = document.getElementById('input-modal-field');
        const confirmBtn = document.getElementById('input-modal-confirm');
        const cancelBtn = document.getElementById('input-modal-cancel');

        if (!modal) return;

        modalTitle.textContent = title;
        inputField.placeholder = placeholder;
        inputField.value = defaultValue || '';

        // Show modal and focus input
        modal.classList.remove('hidden');
        requestAnimationFrame(() => {
            modal.classList.add('active');
            inputField.focus();
            inputField.select();
        });

        const closeModal = () => {
            modal.classList.remove('active');
            setTimeout(() => {
                modal.classList.add('hidden');
            }, 200);
        };

        const handleConfirm = () => {
            const value = inputField.value.trim();
            if (value) {
                onConfirm(value);
            }
            closeModal();
        };

        const handleCancel = () => {
            closeModal();
        };

        // Handle Enter/Escape keys
        const handleKeydown = (e) => {
            if (e.key === 'Enter') {
                handleConfirm();
            } else if (e.key === 'Escape') {
                handleCancel();
            }
        };

        confirmBtn.onclick = handleConfirm;
        cancelBtn.onclick = handleCancel;
        inputField.onkeydown = handleKeydown;
    }

    // =========================================================================
    // TOAST NOTIFICATIONS
    // =========================================================================

    /**
     * Shows a temporary toast notification.
     * Auto-hides after 3 seconds.
     * 
     * @param {string} message - Message to display
     */
    function showToast(message) {
        const toast = document.getElementById('toast-notification');
        const toastMessage = document.getElementById('toast-message');

        if (!toast) return;

        toastMessage.textContent = message;
        toast.classList.remove('hidden');

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto-hide after 3 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.classList.add('hidden');
            }, 300);
        }, 3000);
    }

    // =========================================================================
    // UTILITY FUNCTIONS
    // =========================================================================

    /**
     * Escapes HTML special characters to prevent XSS.
     * 
     * @param {string} text - Raw text to escape
     * @returns {string} Escaped HTML-safe string
     */
    function escapeHtml(text) {
        if (!text) return '';
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
