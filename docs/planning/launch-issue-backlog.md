# Launch Issue Backlog (Good First Issues)

Welcome to Kinthic! If you are looking to contribute to the project during our launch window, the following 20 issues are great places to start. They are scoped to be approachable for new contributors.

## Tool & Plugin Ecosystem
1. **[Tool] Jira MCP Integration**: Create an MCP preset for querying and updating Jira tickets.
2. **[Tool] Slack Adapter**: Build an alternative to the Telegram adapter for Slack workspaces.
3. **[Tool] AWS CLI Wrapper Tool**: Add a tool plugin that allows the agent to securely list EC2 instances.
4. **[Provider] Groq Support**: Add a `plugins/providers/groq` preset for fast inference.
5. **[Skill] Code Reviewer Pro**: Expand the bundled code_reviewer skill to specifically check for OWASP top 10 vulnerabilities.

## Core Framework
6. **[Memory] Prune TTL**: Implement a TTL (Time To Live) feature in the `sqlite` graph for ephemeral memories.
7. **[Memory] Vector Fallback**: Add basic cosine similarity search using `sqlite-vss` for when keyword search fails.
8. **[CLI] Colorful output**: Add `rich` syntax highlighting to `kinthic doctor` output.
9. **[CLI] Setup retry**: Allow users to retry entering their API key in `kinthic onboard` if the validation ping fails.
10. **[Router] Token Thresholds**: Allow configuring a max token threshold in SmartRouter before forcing the fallback model.

## UI / UX (Telegram)
11. **[UX] Typing Indicator**: Send a `sendChatAction(TYPING)` to Telegram while the agent is "thinking".
12. **[UX] Markdown parsing**: Fix Telegram parse mode edge cases where nested markdown blocks cause API errors.
13. **[UX] Pagination**: Add pagination to `/usage` command output if it exceeds message limits.
14. **[UX] Inline Buttons**: Replace text-based `/approve` and `/reject` commands with Telegram InlineKeyboardButtons.
15. **[UX] Goal Progress**: Send a periodic status message when a background goal takes longer than 5 minutes.

## Documentation & Testing
16. **[Docs] WSL2 Guide**: Write a detailed step-by-step guide for Windows users installing via WSL2.
17. **[Docs] MCP Examples**: Document 3 complete examples of connecting to community MCP servers.
18. **[Test] SQLite Graph**: Increase test coverage of edge creation and deletion in `silex.memory.graph`.
19. **[Test] Telegram Mock**: Add a mocked update test for the Telegram rate limiter.
20. **[Test] Migration Scripts**: Add more robust JSON5 parsing tests for the OpenClaw migration script.
