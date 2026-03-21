"use client"

import { fetcher } from "@/utils/fetcher";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

export default function Home() {
  const router = useRouter()
  const { data } = useSWR({ url: `chat` }, fetcher) // make GET request

  async function createChat() { // make POST request
    const resp = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({}),
    })

    if (resp.ok) {
      const json = await resp.json()
      router.push(`/${json.id}`)
    }
  }

  return <div className="m-4 p-4 rounded-lg"><div className="flex justify-between items-center mb-4">
    <h1 className="text-2xl font-semibold">Chats</h1>
    <button className="justify-center rounded-md px-4 py-2 text-sm font-medium text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-opacity-75 bg-blue-950 bg-opacity-50 hover:bg-opacity-70" onClick={() => createChat()}>Create Chat</button>
  </div>
    <div className="border rounded-lg border-neutral-300 bg-white p-4 shadow">
      <div className="w-full text-sm text-left table">
        <div className="text-xs uppercase table-header-group">
          <div className="table-row">
            <div className="font-semibold table-cell px-3 py-3">
              ID
            </div>
            <div className="font-semibold table-cell px-3 py-3">
              Created At
            </div>
          </div>
        </div>
        <div className="table-row-group">
          {data?.map((s: any) => {
            const date = new Date(s.created_at + 'Z')
            return (
              <Link key={`${s.user_id}:${s.resource_id}`} href={`/${s.id}`} className="border-b hover:bg-neutral-200 hover:cursor-pointer table-row align-middle">
                <div className="px-3 py-3 table-cell font-medium text-gray-900 whitespace-nowrap ">
                  {s.id}
                </div>
                <div className="table-cell px-3 py-3">
                  <div className="flex justify-between items-center">
                    {date.toLocaleString()}
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  </div>



  // }

  // return (
  //   <main className="flex min-h-screen flex-col items-center space-y-4 p-24">
  //     <h1 className="text-xl font-semibold">Chat Window</h1>
  //     <div className="grow w-1/2 border border-gray-300 bg-gray-50 flex flex-col-reverse rounded-lg overflow-y-scroll">
  //       <OpenAIConversationDisplay messages={messages} />
  //     </div>
  //     <div className="flex w-1/2 space-x-2">
  //       <input type="text" onChange={(e) => setInput(e.target.value)} value={input} className="bg-gray-50 grow border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block p-2.5" />
  //       <button onClick={() => generateResponse()} className="text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:outline-none focus:ring-blue-300 font-medium rounded-lg text-sm w-full sm:w-auto px-5 py-2.5 text-center dark:bg-blue-600 dark:hover:bg-blue-700 dark:focus:ring-blue-800">Send</button>
  //     </div>
  //   </main>
  // );
}
