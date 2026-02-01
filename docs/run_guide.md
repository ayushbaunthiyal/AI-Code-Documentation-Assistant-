# 🏃 Run Guide: AI Code Documentation Assistant

This guide covers how to set up and run the **AI Code Documentation Assistant** from a fresh machine.

## 📋 Prerequisites

Before you start, ensure you have the following installed:

1.  **Docker Desktop** (essential for running Memgraph and the App).
    *   [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)
2.  **Git** (to clone this repository).
    *   [Download Git](https://git-scm.com/downloads)
3.  **OpenAI API Key** (required for the AI Agent).
    *   [Get API Key](https://platform.openai.com/api-keys)

---

## 🚀 Step-by-Step Setup

### 1. Clone the Repository
Open your terminal (PowerShell, Command Prompt, or Terminal) and run:

```bash
git clone https://github.com/your-username/AI-Code-Documentation-Assistant.git
cd AI-Code-Documentation-Assistant
```
*(Replace `your-username` with the actual path if you haven't pushed it yet, or just navigate to the folder if you downloaded the zip)*

### 2. Configure Environment Variables
The application needs your API key to function.

1.  Locate the `.env.example` file in the root directory.
2.  Copy it to a new file named `.env`.
    *   **Windows (PowerShell)**: `Copy-Item .env.example .env`
    *   **Mac/Linux**: `cp .env.example .env`
3.  Open `.env` in a text editor (Notepad, VS Code, etc.).
4.  Find the line `OPENAI_API_KEY=sk-proj-example...`.
5.  Replace the value with your actual key:
    ```ini
    OPENAI_API_KEY=sk-proj-1234567890abcdef...
    ```
6.  Save dependencies.

### 3. Build and Start the System
We use **Docker Compose** to spin up all 3 services (Database, Backend Server, Frontend UI) at once.

Run this command in the project root:

```bash
docker-compose up --build
```

**What happens next?**
*   **Step 1**: It will download the **Memgraph** database image.
*   **Step 2**: It will build the **MCP Server** (installing Python dependencies with `uv`).
*   **Step 3**: It will build the **Client App** (installing Streamlit).
*   **Step 4**: It will start the services.

*Note: The first run might take 2-5 minutes depending on your internet speed.*

Wait until you see logs like:
> `client-1 | You can now view your Streamlit app in your browser.`
> `mcp_server-1 | INFO: Starting MCP Server...`

### 4. Access the Application

*   **User Interface**: Open your browser and go to **[http://localhost:8503](http://localhost:8503)**.
*   **Database Dashboard** (Optional): Go to **[http://localhost:3000](http://localhost:3000)** (User: `memgraph`, Pass: `memgraph`) to see the raw graph data.

---

## 🧪 How to Use

1.  **Enter a Repo**:
    In the Streamlit UI, paste a GitHub URL (e.g., `https://github.com/pallets/flask`) inside the "GitHub Repository URL" box.
2.  **Start Analysis**:
    Click the "Start Analysis" button.
    *   *Wait for the spinner to finish. The system is cloning the code and building the Knowledge Graph.*
3.  **Chat**:
    Once finished, ask a question like:
    *   "How does the routing logic work?"
    *   "What are the main dependencies?"
    *   "Explain the authentication flow."

---

## 🛑 Stopping the App

To stop the application, go back to your terminal and press `Ctrl + C`.

To remove the containers and clean up:
```bash
docker-compose down
```

## 🛠 Troubleshooting

*   **Port Conflicts**: If it says "Port 8503 is already in use", you can change the port in `docker-compose.yml` under `client`.
*   **OpenAI Errors**: Double-check your `.env` file to ensure the API key is correct and has no extra spaces.
*   **Memgraph Connection**: If the server fails to connect to DB, ensure Docker is actually running.
