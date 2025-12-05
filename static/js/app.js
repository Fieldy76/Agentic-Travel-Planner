document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatContainer = document.getElementById('chat-container');
    const sendBtn = document.getElementById('send-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const statusDot = statusIndicator.querySelector('.status-dot');
    const statusText = statusIndicator.querySelector('.status-text');
    const historyToggle = document.getElementById('history-toggle');
    const historySidebar = document.getElementById('history-sidebar');
    const historyList = document.getElementById('history-list');
    const clearHistoryBtn = document.getElementById('clear-history');

    let isProcessing = false;
    let searchHistory = loadSearchHistory();
    let currentConversationId = null;
    let conversationMessages = [];

    // Initialize history display
    renderHistory();

    const fileInput = document.getElementById('file-input');
    // const attachBtn = document.querySelector('.attach-btn'); // Removed
    let selectedFile = null;

    // Toggle history sidebar
    historyToggle.addEventListener('click', () => {
        historySidebar.classList.toggle('collapsed');
    });

    const menuBtn = document.getElementById('attach-menu-btn');
    const menu = document.getElementById('attachment-menu');

    // Toggle Menu
    menuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('active');
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!menu.contains(e.target) && !menuBtn.contains(e.target)) {
            menu.classList.remove('active');
        }
    });

    // Handle File Selection (Label triggers input, but we also want to close menu)
    fileInput.addEventListener('click', () => {
        menu.classList.remove('active');
    });

    // Extracted logic for UI Update
    function updateFilePill(file) {
        let existingPill = document.querySelector('.file-pill');
        if (existingPill) existingPill.remove();

        const pill = document.createElement('div');
        pill.className = 'file-pill';
        pill.innerHTML = `
            <span class="file-name">${file.name}</span>
            <button type="button" class="remove-file">×</button>
        `;

        chatForm.insertBefore(pill, userInput);

        pill.querySelector('.remove-file').addEventListener('click', () => {
            selectedFile = null;
            if (fileInput) fileInput.value = '';
            pill.remove();
        });

        userInput.focus();
    }

    // File Selection
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            selectedFile = e.target.files[0];
            updateFilePill(selectedFile);
        }
    });

    // Clear history
    clearHistoryBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to clear all search history?')) {
            searchHistory = [];
            saveSearchHistory();
            renderHistory();

            // Also clear all chat messages and start new conversation
            startNewConversation();
        }
    });

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        let message = userInput.value.trim();

        // Handle attachment text
        if (selectedFile) {
            message = `[Attached: ${selectedFile.name}] ${message}`.trim();
            // Reset file input
            selectedFile = null;
            fileInput.value = '';
            const pill = document.querySelector('.file-pill');
            if (pill) pill.remove();
        }

        if (!message || isProcessing) return;

        // Switch UI to active conversation mode
        chatContainer.classList.add('has-messages');

        // If starting a new conversation, create a history entry
        if (currentConversationId === null) {
            currentConversationId = Date.now().toString();
            // We'll add it to history after we get a response or immediately?
            // Let's add immediately to track it.
            addConversationToHistory(message);
        }

        // Add User Message
        appendMessage('user', message);
        saveCurrentConversation(); // Save state

        userInput.value = '';
        setProcessing(true);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');

                // Process all complete lines
                buffer = lines.pop();

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
            setProcessing(false);
            saveCurrentConversation(); // Save final state
        }
    });

    function handleEvent(event) {
        switch (event.type) {
            case 'message':
                // Only show messages that don't contain raw tool output
                if (!event.content.includes('```tool_outputs')) {
                    appendMessage('assistant', event.content);
                }
                break;
            case 'tool_call':
                appendToolCall(event.name, event.arguments);
                break;
            case 'tool_result':
                // Just update the status, don't display the raw result
                updateToolResult(event.name, event.content, event.is_error);
                break;
            case 'error':
                appendMessage('assistant', `Error: ${event.content}`);
                break;
        }
    }

    function appendMessage(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Render Markdown links: [text](url) -> <a href="url" target="_blank">text</a>
        // Also handle newlines
        let formattedContent = escapeHtml(content)
            .replace(/\n/g, '<br>')
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

        contentDiv.innerHTML = formattedContent;

        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);
        scrollToBottom();

        // Update internal state
        conversationMessages.push({ role, content });
    }

    function appendToolCall(name, args) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call';
        toolDiv.id = `tool-${Date.now()}`; // Simple ID generation

        // Get friendly display text
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

        // Store reference to update later
        window.lastToolDiv = toolDiv;

        // Add to history state (simplified)
        conversationMessages.push({
            role: 'tool_call_ui',
            name,
            args,
            displayInfo
        });
    }

    function getToolDisplayInfo(name, args) {
        // Return friendly display text based on tool type
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

    function formatToolName(name) {
        return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    }

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function setProcessing(processing) {
        isProcessing = processing;
        userInput.disabled = processing;
        sendBtn.disabled = processing;

        if (processing) {
            statusDot.classList.add('busy');
            statusText.textContent = 'Thinking...';

            // Add "Thinking" bubble
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

    // Search History Functions
    function loadSearchHistory() {
        try {
            const saved = localStorage.getItem('travelSearchHistory');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            console.error('Error loading search history:', e);
            return [];
        }
    }

    function saveSearchHistory() {
        try {
            localStorage.setItem('travelSearchHistory', JSON.stringify(searchHistory));
        } catch (e) {
            console.error('Error saving search history:', e);
        }
    }

    function saveCurrentConversation() {
        if (!currentConversationId) return;

        const index = searchHistory.findIndex(c => c.id === currentConversationId);
        if (index !== -1) {
            searchHistory[index].messages = conversationMessages;
            saveSearchHistory();
        }
    }

    function addConversationToHistory(firstMessage) {
        const conversationItem = {
            id: currentConversationId,
            title: firstMessage.length > 50 ? firstMessage.substring(0, 50) + '...' : firstMessage,
            timestamp: new Date().toISOString(),
            messages: [] // Will be populated as we go
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

    function startNewConversation() {
        // Clear current conversation
        chatContainer.innerHTML = '';
        chatContainer.classList.remove('has-messages');
        // Restore welcome message if it was hidden via innerHTML clearing? 
        // Wait, clearing innerHTML remvoes the welcome message div itself!
        // I need to NOT clear the welcome message if I want it back, OR re-inject it.
        // Actually, the welcome message is STATIC in HTML.
        // If I do chatContainer.innerHTML = '', I delete the static welcome message.
        // I should probably Restore it.

        chatContainer.innerHTML = `
            <div class="welcome-message">
                <div class="hero-text">
                    <span class="gradient-text">Hello, Traveler</span>
                </div>
                <p class="subtitle">How can I help you explore the world today?</p>
            </div>
        `;
        currentConversationId = null;
        conversationMessages = [];
        userInput.value = '';
        userInput.focus();

        // Remove active class from history
        document.querySelectorAll('.history-item').forEach(item => item.classList.remove('active'));
    }

    function loadConversation(id) {
        const conversation = searchHistory.find(c => c.id === id);
        if (!conversation) return;

        currentConversationId = id;
        conversationMessages = conversation.messages || [];

        // Clear and rebuild chat
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

        // Replay messages
        conversationMessages.forEach(msg => {
            if (msg.role === 'tool_call_ui') {
                // Reconstruct tool call UI
                const toolDiv = document.createElement('div');
                toolDiv.className = 'tool-call';
                // We don't need ID for history items really

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

        // Remove duplicate messages from state (appendMessage adds them again)
        // Actually appendMessage adds to conversationMessages, so we should reset it before replaying
        // But wait, appendMessage pushes to conversationMessages. 
        // So if we loop and call appendMessage, we are doubling the array.
        // Let's fix this by decoupling UI rendering from state update in appendMessage, 
        // OR just reset conversationMessages after replaying?
        // Better: make appendMessage NOT update state, handle state separately.
        // But for now, let's just reset it to the loaded messages after replaying.
        conversationMessages = conversation.messages || [];

        scrollToBottom();
        renderHistory();
    }

    function deleteConversation(id, event) {
        event.stopPropagation(); // Prevent clicking the item
        if (confirm('Delete this conversation?')) {
            searchHistory = searchHistory.filter(c => c.id !== id);
            saveSearchHistory();
            renderHistory();

            if (currentConversationId === id) {
                startNewConversation();
            }
        }
    }

    function renderHistory() {
        if (searchHistory.length === 0) {
            historyList.innerHTML = '<div class="history-empty">No search history yet</div>';
            return;
        }

        historyList.innerHTML = '';
        searchHistory.forEach((conversation) => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';

            // Add active class if this is the current conversation
            if (conversation.id === currentConversationId) {
                historyItem.classList.add('active');
            }

            historyItem.innerHTML = `
                <div class="history-item-content">
                    <div class="history-item-text">${escapeHtml(conversation.title)}</div>
                    <div class="history-item-time">${formatTimestamp(conversation.timestamp)}</div>
                </div>
                <button class="delete-history-btn" title="Delete">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                </button>
            `;

            historyItem.addEventListener('click', () => {
                loadConversation(conversation.id);
            });

            // Add delete handler
            const deleteBtn = historyItem.querySelector('.delete-history-btn');
            deleteBtn.addEventListener('click', (e) => deleteConversation(conversation.id, e));

            historyList.appendChild(historyItem);
        });
    }

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
