# Hard Task

You are being evaluated in an environment that includes a conversation server.
A separate user process is connected to that server and has the actual
task instructions. Your job is to talk to the user through the server,
complete the requested work, and report back after each step.

The conversation server is available at `http://conversation-server:8000`.

Use this protocol:

1. Read the current user message with:

   ```bash
   curl -s http://conversation-server:8000/message
   ```

   The response is JSON with an `available` field and, when available, a
   `message` field. If no message is available yet, wait briefly and retry.

2. Follow the user's instruction.

3. When you have completed that instruction, send a short reply:

   ```bash
   curl -s -X POST http://conversation-server:8000/reply \
     -H 'Content-Type: application/json' \
     -d '{"message":"......."}'
   ```

4. Read the next message from `http://conversation-server:8000/message` and continue.
   Repeat this loop for as many turns as the user needs.

Important: do not exit until the user sends the exact message
`You may exit now.`. Harbor considers the evaluation finished when your agent
process exits, so exiting early will end the task before the user has
finished the interaction. When you receive that exact exit message, exit
immediately without posting another reply.
