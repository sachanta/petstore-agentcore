import { useState } from "react";
import { sendMessage } from "./api";
import type { ChatMessage } from "./types";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";
import { ChatInput } from "./components/ChatInput";

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput]       = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async (overridePrompt?: string) => {
    const prompt = (overridePrompt ?? input).trim();
    if (!prompt || isLoading) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: prompt,
    };

    const placeholderId = crypto.randomUUID();
    const placeholder: ChatMessage = {
      id: placeholderId,
      role: "agent",
      loading: true,
    };

    setMessages((prev) => [...prev, userMsg, placeholder]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await sendMessage(prompt);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === placeholderId ? { ...m, loading: false, response } : m
        )
      );
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Something went wrong";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === placeholderId
            ? {
                ...m,
                loading: false,
                response: {
                  status: "Error",
                  message: `We're sorry, there was a problem reaching the assistant. ${errorMsg}`,
                },
              }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full bg-white">
      <Sidebar onPromptSelect={(p) => handleSend(p)} disabled={isLoading} />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <header className="shrink-0 px-6 py-3.5 border-b border-gray-200 flex items-center justify-between">
          <h1 className="font-semibold text-gray-800">Staff Order Assistant</h1>
          <span className="h-2 w-2 rounded-full bg-brand-500 animate-pulse" title="Runtime active" />
        </header>

        <ChatArea messages={messages} />

        <ChatInput
          value={input}
          onChange={setInput}
          onSend={() => handleSend()}
          disabled={isLoading}
        />
      </div>
    </div>
  );
}
