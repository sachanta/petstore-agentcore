import type { ChatMessage } from "../types";
import { AgentResponseCard } from "./AgentResponseCard";

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-lg rounded-2xl bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {message.text}
        </div>
      </div>
    );
  }

  if (message.loading) {
    return (
      <div className="flex items-center gap-1.5 py-2">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      {message.response && <AgentResponseCard response={message.response} />}
    </div>
  );
}
