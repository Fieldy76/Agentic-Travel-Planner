document.addEventListener('DOMContentLoaded', () => {
    // Wait for the DOM to be fully loaded before executing the script
    const chatForm = document.getElementById('chat-form'); // Get the chat form element
    const userInput = document.getElementById('user-input'); // Get the user input field
    const chatContainer = document.getElementById('chat-container'); // Get the container for chat messages
    const sendBtn = document.getElementById('send-btn'); // Get the send button
    const statusIndicator = document.getElementById('status-indicator'); // Get the status indicator container
    const statusDot = statusIndicator.querySelector('.status-dot'); // Get the status dot element
    const statusText = statusIndicator.querySelector('.status-text'); // Get the status text element

    let isProcessing = false; // Flag to track if a request is currently being processed

    chatForm.addEventListener('submit', async (e) => {
        // Add event listener for form submission
        e.preventDefault(); // Prevent default form submission (page reload)
        const message = userInput.value.trim(); // Get and trim the user's message
        if (!message || isProcessing) return; // Exit if message is empty or already processing

        // Add User Message to UI
        appendMessage('user', message);
        userInput.value = ''; // Clear input field
        setProcessing(true); // Set processing state to true

        try {
            // Send POST request to the chat API
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message }) // Send message as JSON
            });

            const reader = response.body.getReader(); // Get a reader for the response stream
            const decoder = new TextDecoder(); // Create a TextDecoder to decode binary chunks
            let buffer = ''; // Buffer to hold incomplete lines

            while (true) {
                const { done, value } = await reader.read(); // Read the next chunk
                if (done) break; // Exit loop if stream is finished

                buffer += decoder.decode(value, { stream: true }); // Decode chunk and append to buffer
                const lines = buffer.split('\n'); // Split buffer into lines

                // Process all complete lines
                buffer = lines.pop(); // Keep the last (potentially incomplete) line in the buffer

                for (const line of lines) {
                    if (line.trim()) { // If line is not empty
                        try {
                            const event = JSON.parse(line); // Parse JSON event
                            handleEvent(event); // Handle the event
                        } catch (e) {
                            console.error('Error parsing JSON:', e); // Log parsing errors
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error:', error); // Log network or other errors
            appendMessage('assistant', 'Sorry, something went wrong. Please try again.'); // Show error message to user
        } finally {
            setProcessing(false); // Reset processing state
        }
    });

    function handleEvent(event) {
        // Dispatch events to appropriate handlers based on type
        switch (event.type) {
            case 'message':
                appendMessage('assistant', event.content); // Append assistant message
                break;
            case 'tool_call':
                appendToolCall(event.name, event.arguments); // Append tool call display
                break;
            case 'tool_result':
                updateToolResult(event.name, event.content, event.is_error); // Update tool call with result
                break;
            case 'error':
                appendMessage('assistant', `Error: ${event.content}`); // Append error message
                break;
        }
    }

    function appendMessage(role, content) {
        // Create and append a message element to the chat container
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`; // Set class based on role (user/assistant)

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content; // Set message text

        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);
        scrollToBottom(); // Scroll to bottom to show new message
    }

    function appendToolCall(name, args) {
        // Create and append a tool call visualization
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call';
        toolDiv.id = `tool-${Date.now()}`; // Generate a simple unique ID

        // Set inner HTML for tool call structure
        toolDiv.innerHTML = `
            <div class="tool-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
            </div>
            <div class="tool-details">
                <div class="tool-name">${formatToolName(name)}</div>
                <div class="tool-args">${JSON.stringify(args)}</div>
            </div>
            <div class="tool-status running">Running</div>
        `;

        chatContainer.appendChild(toolDiv);
        scrollToBottom();

        // Store reference to update later (simplification: assuming sequential tool calls for now)
        window.lastToolDiv = toolDiv;
    }

    function updateToolResult(name, content, isError) {
        // Update the status of the last tool call
        if (window.lastToolDiv) {
            const statusDiv = window.lastToolDiv.querySelector('.tool-status');
            statusDiv.classList.remove('running'); // Remove running class

            if (isError) {
                statusDiv.textContent = 'Error'; // Set status to Error
                statusDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                statusDiv.style.color = '#ef4444';
            } else {
                statusDiv.textContent = 'Completed'; // Set status to Completed
                statusDiv.style.backgroundColor = 'rgba(34, 197, 94, 0.1)';
                statusDiv.style.color = '#22c55e';
            }
            window.lastToolDiv = null; // Clear reference
        }
    }

    function formatToolName(name) {
        // Format tool name for display (e.g., "search_flights" -> "Search Flights")
        return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    }

    function scrollToBottom() {
        // Scroll the chat container to the bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function setProcessing(processing) {
        // Update UI state based on processing flag
        isProcessing = processing;
        userInput.disabled = processing; // Disable input
        sendBtn.disabled = processing; // Disable button

        if (processing) {
            statusDot.classList.add('busy'); // Set dot to busy
            statusText.textContent = 'Thinking...'; // Update text
        } else {
            statusDot.classList.remove('busy'); // Remove busy state
            statusText.textContent = 'Ready'; // Update text
            userInput.focus(); // Focus input
        }
    }
});
