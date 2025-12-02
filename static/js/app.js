document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatContainer = document.getElementById('chat-container');
    const sendBtn = document.getElementById('send-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const statusDot = statusIndicator.querySelector('.status-dot');
    const statusText = statusIndicator.querySelector('.status-text');

    let isProcessing = false;

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        if (!message || isProcessing) return;

        // Add User Message
        appendMessage('user', message);
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
        }
    });

    function handleEvent(event) {
        switch (event.type) {
            case 'message':
                appendMessage('assistant', event.content);
                break;
            case 'tool_call':
                appendToolCall(event.name, event.arguments);
                break;
            case 'tool_result':
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
        contentDiv.textContent = content;

        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);
        scrollToBottom();
    }

    function appendToolCall(name, args) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call';
        toolDiv.id = `tool-${Date.now()}`; // Simple ID generation

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
        } else {
            statusDot.classList.remove('busy');
            statusText.textContent = 'Ready';
            userInput.focus();
        }
    }
});
