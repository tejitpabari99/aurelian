class RequestError extends Error {
  info: string | undefined;
  status: number | undefined;
}

export async function fetcher(args: { url: string }) {
  const r = await fetch(`http://localhost:8000/${args.url}`);

  if (!r.ok) {
    const error = new RequestError("An error occurred while fetching data");
    error.info = await r.json();
    error.status = r.status;
    throw error;
  }

  return await r.json();
}
