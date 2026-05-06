import { PawPrint, Sparkles } from "lucide-react";

const EXAMPLE_PROMPTS = [
  "What is the price of Doggy Delights?",
  "I want 2 Bark Park Buddy water bottles",
  "Do you have a self-cleaning litter box?",
  "I want the SmartFeed Automatic Dog Feeder",
  "CustomerId: usr_001 — I want the Bark Park Buddy. Good for bathing my dog?",
  "I want the CleanPaws Litter Box and SmartFeed Feeder",
];

interface Props {
  onPromptSelect: (prompt: string) => void;
  disabled: boolean;
}

export function Sidebar({ onPromptSelect, disabled }: Props) {
  return (
    <aside className="flex flex-col h-full bg-gray-50 border-r border-gray-200 w-72 shrink-0">
      {/* Branding */}
      <div className="px-5 py-5 border-b border-gray-200">
        <div className="flex items-center gap-2.5">
          <div className="rounded-xl bg-brand-600 p-2 text-white">
            <PawPrint size={20} />
          </div>
          <div>
            <p className="font-semibold text-gray-900 leading-tight">PetStore AI</p>
            <p className="text-xs text-gray-500">Staff Assistant</p>
          </div>
        </div>
      </div>

      {/* Example prompts */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        <div className="flex items-center gap-1.5 mb-3">
          <Sparkles size={13} className="text-brand-500" />
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Try asking…</p>
        </div>
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onPromptSelect(prompt)}
            disabled={disabled}
            className="w-full text-left rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-700 hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-gray-200">
        <p className="text-xs text-gray-400 text-center">
          Powered by Amazon Bedrock AgentCore
        </p>
      </div>
    </aside>
  );
}
