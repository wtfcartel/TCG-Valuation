export class HttpError extends Error {
  constructor(
    readonly statusCode: number,
    message: string,
    readonly code = "error",
  ) {
    super(message);
  }
}

export const notFound = (what: string) => new HttpError(404, `${what} not found`, "not_found");
export const badRequest = (message: string) => new HttpError(400, message, "bad_request");
export const conflict = (message: string) => new HttpError(409, message, "conflict");
export const forbidden = (message = "Forbidden") => new HttpError(403, message, "forbidden");
