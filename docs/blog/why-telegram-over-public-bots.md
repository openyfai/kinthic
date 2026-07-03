# Why We Chose Paired Telegram Over Public Bots

When we set out to build Kronos, one of the first architectural decisions we faced was how users would interact with the agent. 

The industry standard for agentic platforms (like OpenClaw or Hermes) is to expose a public REST API or a web UI served over localhost. If you want to access your agent on the go, you have to expose that port to the internet—often resulting in complex authentication proxy setups, or worse, leaving it entirely unprotected.

**We chose a different path: Telegram.**

Here is why Kronos uses a paired Telegram bot architecture instead of a traditional web API.

## 1. Zero Ingress, Maximum Security
Kronos runs entirely behind your firewall. The `kronos daemon` connects *outbound* to Telegram's long-polling API. You do not need to open any ports, configure port-forwarding, or set up dynamic DNS. 

Because there is no open port on your machine, there is zero surface area for automated scanners and botnets to exploit.

## 2. Hardened Authentication (The Pairing Protocol)
Just having a Telegram bot isn't enough; if someone finds your bot's username, they could interact with it.

Kronos uses a strict pairing protocol. When you first start the daemon, it generates a secure, one-time pairing PIN. You must message that PIN to the bot within a 15-minute window. Once paired, Kronos maps your specific Telegram `user_id` to the `operator` role. 

Any message from an unpaired user is immediately dropped, and repeated attempts trigger a strict rate limiter (max 5 attempts per minute). 

## 3. The `/approve` Loop
Agents are dangerous. They execute code, modify files, and access APIs.

By putting the interface in your pocket, Kronos ensures you are always in the loop. If the agent needs to perform an irreversible action (like modifying a production database via an MCP server or installing a new workflow skill), it pauses execution and sends an approval request to your phone. 

You can review the action, tap `/approve` or `/reject`, and the agent resumes exactly where it left off.

## Conclusion
Kronos isn't trying to be a SaaS. It's a personal, private cognitive engine. By leveraging Telegram, we provide a world-class mobile and desktop UX without compromising the security of your local network.
