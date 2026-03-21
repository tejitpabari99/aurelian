"use client"

import { fetcher } from "@/utils/fetcher";
import { useEffect, useState, useCallback } from "react";
import useSWR from "swr";

interface FormSubmissionData {
  id: string;
  created_at: string;
  name: string;
  phone_number: string;
  email: string;
  status: number | null;
}

const STATUS_LABELS: Record<number, string> = {
  1: "TO DO",
  2: "IN PROGRESS",
  3: "COMPLETED",
};

const STATUS_COLORS: Record<number, string> = {
  1: "bg-yellow-100 text-yellow-800",
  2: "bg-blue-100 text-blue-800",
  3: "bg-green-100 text-green-800",
};

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
        // Skip assistant messages that are only tool calls (no visible text)
        if (s.tool_calls) {
          return null;
        }
        // Skip if there's no content to display
        if (!s.content) {
          return null;
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
      // Hide tool response messages from the user
      if (s.role == "tool") {
        return null;
      }

    })}
  </div>
}

function FormCard({
  form,
  onUpdate,
  onDelete,
}: {
  form: FormSubmissionData;
  onUpdate: (id: string, data: Partial<FormSubmissionData>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editName, setEditName] = useState(form.name);
  const [editEmail, setEditEmail] = useState(form.email);
  const [editPhone, setEditPhone] = useState(form.phone_number);
  const [editStatus, setEditStatus] = useState<number | null>(form.status);

  const date = new Date(form.created_at + "Z");

  function startEdit() {
    setEditName(form.name);
    setEditEmail(form.email);
    setEditPhone(form.phone_number);
    setEditStatus(form.status);
    setEditing(true);
  }

  async function saveEdit() {
    setSaving(true);
    try {
      await onUpdate(form.id, {
        name: editName,
        email: editEmail,
        phone_number: editPhone,
        status: editStatus,
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    setSaving(true);
    try {
      await onDelete(form.id);
    } finally {
      setSaving(false);
      setDeleting(false);
    }
  }

  if (editing) {
    return (
      <div className="border border-blue-300 bg-blue-50 rounded-lg p-3 shadow-sm text-sm">
        <div className="space-y-2">
          <div>
            <label className="text-xs text-gray-500">Name</label>
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500">Email</label>
            <input
              type="text"
              value={editEmail}
              onChange={(e) => setEditEmail(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500">Phone</label>
            <input
              type="text"
              value={editPhone}
              onChange={(e) => setEditPhone(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500">Status</label>
            <select
              value={editStatus ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                setEditStatus(v === "" ? null : parseInt(v));
              }}
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
            >
              <option value="">None</option>
              <option value="1">TO DO</option>
              <option value="2">IN PROGRESS</option>
              <option value="3">COMPLETED</option>
            </select>
          </div>
        </div>
        <div className="flex space-x-2 mt-3">
          <button
            onClick={saveEdit}
            disabled={saving}
            className="flex-1 text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={saving}
            className="flex-1 text-xs px-2 py-1 rounded bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-gray-300 bg-white rounded-lg p-3 shadow-sm text-sm">
      <div className="flex justify-between items-start mb-2">
        <span className="font-semibold text-gray-900">{form.name || "—"}</span>
        <span className="text-xs text-gray-400">{date.toLocaleString()}</span>
      </div>
      <div className="space-y-1 text-gray-700">
        <div className="flex items-center space-x-2">
          <span className="text-gray-400 text-xs w-14">Email</span>
          <span>{form.email || "—"}</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-gray-400 text-xs w-14">Phone</span>
          <span>{form.phone_number || "—"}</span>
        </div>
      </div>
      <div className="mt-2 pt-2 border-t border-gray-100 flex justify-between items-center">
        <span className="text-xs text-gray-400 font-mono truncate mr-1" title={form.id}>
          ID: {form.id}
        </span>
        {form.status !== null && form.status in STATUS_LABELS ? (
          <span
            className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${STATUS_COLORS[form.status] ?? "bg-gray-100 text-gray-700"}`}
          >
            {STATUS_LABELS[form.status]}
          </span>
        ) : form.status !== null ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">
            Status: {form.status}
          </span>
        ) : null}
      </div>

      {/* Action buttons */}
      <div className="mt-2 pt-2 border-t border-gray-100 flex space-x-2">
        {deleting ? (
          <>
            <span className="text-xs text-red-600 flex-1">Delete this form?</span>
            <button
              onClick={confirmDelete}
              disabled={saving}
              className="text-xs px-2 py-0.5 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
            >
              {saving ? "…" : "Yes"}
            </button>
            <button
              onClick={() => setDeleting(false)}
              disabled={saving}
              className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50"
            >
              No
            </button>
          </>
        ) : (
          <>
            <button
              onClick={startEdit}
              className="flex-1 text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
            >
              Edit
            </button>
            <button
              onClick={() => setDeleting(true)}
              className="flex-1 text-xs px-2 py-0.5 rounded bg-red-50 text-red-600 hover:bg-red-100"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function FormSubmissionsPanel({
  formSubmissions,
  onUpdate,
  onDelete,
}: {
  formSubmissions: FormSubmissionData[];
  onUpdate: (id: string, data: Partial<FormSubmissionData>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  if (formSubmissions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm">
        <p>No form submissions yet.</p>
        <p className="mt-1 text-xs">Ask the assistant to submit an interest form.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 overflow-y-auto p-2">
      {formSubmissions.map((form) => (
        <FormCard
          key={form.id}
          form={form}
          onUpdate={onUpdate}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

export default function Home({ params }: { params: { chatId: string } }) {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<any[]>([])
  const [formSubmissions, setFormSubmissions] = useState<FormSubmissionData[]>([])
  const [statusFilter, setStatusFilter] = useState<number | null>(null)
  const { data } = useSWR({url: `chat/${params.chatId}`}, fetcher)

  useEffect(() => {
    if (data) {
        setMessages(data.messages)
        setFormSubmissions(data.form_submissions ?? [])
    }
  }, [data])

  // Fetch forms for this chat, optionally filtered by status
  const refreshForms = useCallback(async () => {
    const url = statusFilter !== null
      ? `http://localhost:8000/chat/${params.chatId}/forms?status=${statusFilter}`
      : `http://localhost:8000/chat/${params.chatId}/forms`;
    const resp = await fetch(url);
    if (resp.ok) {
      const forms = await resp.json();
      setFormSubmissions(forms);
    }
  }, [params.chatId, statusFilter]);

  // Re-fetch forms whenever statusFilter changes
  useEffect(() => {
    if (data) {
      refreshForms();
    }
  }, [statusFilter, refreshForms, data]);

  async function handleUpdateForm(formId: string, updateData: Partial<FormSubmissionData>) {
    const resp = await fetch(`http://localhost:8000/form/${formId}`, {
      method: 'PUT',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updateData),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => null);
      const msg = err?.detail ?? "Failed to update form";
      alert(typeof msg === "string" ? msg : JSON.stringify(msg));
      return;
    }
    await refreshForms();
  }

  async function handleDeleteForm(formId: string) {
    const resp = await fetch(`http://localhost:8000/form/${formId}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' },
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => null);
      const msg = err?.detail ?? "Failed to delete form";
      alert(typeof msg === "string" ? msg : JSON.stringify(msg));
      return;
    }
    await refreshForms();
  }

  async function generateResponse() {
    if (!input) {
      return
    }

    const newMessages = [...messages, { "role": "user", "content": input }]
    setMessages(newMessages)
    setInput("")

    const reqData = {
      messages: newMessages
    }

    const resp = await fetch(`http://localhost:8000/chat/${params.chatId}`, {
      method: 'PUT',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(reqData),
    })

    if (resp.ok) {
      const json = await resp.json()
      setMessages(json.messages)
      // After a chat response, refresh forms with current filter applied
      await refreshForms()
    }

  }

  return (
    <main className="flex min-h-screen flex-col items-center space-y-4 p-24">
      <h1 className="text-xl font-semibold">Chat Window</h1>
      <div className="flex w-3/4 grow space-x-4">
        {/* Chat panel */}
        <div className="flex flex-col flex-1 min-w-0">
          <div className="grow border border-gray-300 bg-gray-50 flex flex-col-reverse rounded-lg overflow-y-scroll">
            <OpenAIConversationDisplay messages={messages} />
          </div>
          <div className="flex mt-4 space-x-2">
            <input type="text" onChange={(e) => setInput(e.target.value)} value={input} onKeyDown={(e) => { if (e.key === "Enter") generateResponse() }} className="bg-gray-50 grow border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block p-2.5" />
            <button onClick={() => generateResponse()} className="text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:outline-none focus:ring-blue-300 font-medium rounded-lg text-sm w-full sm:w-auto px-5 py-2.5 text-center dark:bg-blue-600 dark:hover:bg-blue-700 dark:focus:ring-blue-800">Send</button>
          </div>
        </div>

        {/* Form submissions panel */}
        <div className="w-80 flex-shrink-0 border border-gray-300 bg-gray-50 rounded-lg flex flex-col overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-300 bg-gray-100">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-semibold text-gray-700">
                Forms ({formSubmissions.length})
              </h2>
              <select
                value={statusFilter ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setStatusFilter(v === "" ? null : parseInt(v));
                }}
                className="text-xs border border-gray-300 rounded px-1.5 py-0.5 bg-white text-gray-700"
              >
                <option value="">All</option>
                <option value="1">TO DO</option>
                <option value="2">IN PROGRESS</option>
                <option value="3">COMPLETED</option>
              </select>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            <FormSubmissionsPanel
              formSubmissions={formSubmissions}
              onUpdate={handleUpdateForm}
              onDelete={handleDeleteForm}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
