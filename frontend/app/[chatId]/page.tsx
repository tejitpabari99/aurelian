"use client"

import { fetcher } from "@/utils/fetcher";
import { useEffect, useState } from "react";
import useSWR from "swr";

function ToolCallComponent({ message }: { message: any }) {
  if (message.tool_calls) {
    return message.tool_calls.map((s: any, i: number) => {
      return (
        <div
          key={`tool_call_${i}`}
          className={`max-w-md py-2 px-3 text-sm rounded-lg self-end bg-white border border-blue-950 shadow`}
        >
          Calling function <span className="font-mono">{s.function.name}</span>
          <p className="whitespace-pre-wrap font-mono text-sm">{s.function.arguments}</p>
        </div>
      );
    });
  }
}

function ToolResponseComponent({ message }: { message: any }) {
  return <div
    className={`max-w-md py-2 px-3 text-sm rounded-lg self-end bg-white border border-blue-950 shadow`}
  >
    <div className="whitespace-pre-wrap font-mono text-sm">{message.content}</div>
  </div>;
}

function OpenAIConversationDisplay({ messages }: { messages: any[] }) {

  return <div className="space-y-2 flex flex-col pb-4 px-2 overflow-y-scroll">
    {messages.map((s: any, i: number) => {
      if (s.role == "user") {
        return (
          <div
            key={`message_${i}`}
            className={`max-w-md py-2 px-3 text-sm flex items-center rounded-lg shadow self-start bg-red-950 text-white`}
          >
            <div>{s.content}</div>
          </div>
        );
      }
      if (s.role == "assistant") {
        if (s.tool_calls) {
          return <ToolCallComponent message={s} key={`message_${i}`} />;
        }
        return (
          <div
            key={`message_${i}`}
            className={`max-w-md py-2 px-3 text-sm rounded-lg shadow self-end bg-blue-950 text-white`}
          >
            <div>{s.content}</div>
          </div>
        );
      }
      if (s.role == "tool") {
        return <ToolResponseComponent message={s} key={`message_${i}`} />;
      }

    })}
  </div>
}

export default function Home({ params }: { params: { chatId: string } }) {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<any[]>([])
  const { data } = useSWR({url: `chat/${params.chatId}`}, fetcher)

  useEffect(() => {
    if (data) {
        setMessages(data.messages)
    }
  }, [data])

  async function generateResponse() {
    if (!input) {
      return
    }

    const newMessages = [...messages, { "role": "user", "content": input }]
    setMessages(newMessages)
    setInput("")

    const data = {
      messages: newMessages
    }

    const resp = await fetch(`http://localhost:8000/chat/${params.chatId}`, {
      method: 'PUT',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data),
    })

    if (resp.ok) {
      const json = await resp.json()
      setMessages(json.messages)
    }

  }

  return (
    <main className="flex min-h-screen flex-col items-center space-y-4 p-24">
      <h1 className="text-xl font-semibold">Chat Window</h1>
      <div className="grow w-1/2 border border-gray-300 bg-gray-50 flex flex-col-reverse rounded-lg overflow-y-scroll">
        <OpenAIConversationDisplay messages={messages} />
      </div>
      <div className="flex w-1/2 space-x-2">
        <input type="text" onChange={(e) => setInput(e.target.value)} value={input} className="bg-gray-50 grow border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block p-2.5" />
        <button onClick={() => generateResponse()} className="text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:outline-none focus:ring-blue-300 font-medium rounded-lg text-sm w-full sm:w-auto px-5 py-2.5 text-center dark:bg-blue-600 dark:hover:bg-blue-700 dark:focus:ring-blue-800">Send</button>
      </div>
    </main>
  );
}
