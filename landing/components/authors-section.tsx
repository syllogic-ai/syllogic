"use client";

import Image from "next/image";
import { AUTHORS } from "@/lib/authors";

function LinkedInIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.742l7.73-8.835L1.254 2.25H8.08l4.259 5.63 5.905-5.63zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}


function AuthorAvatar({
  photo,
  initials,
  name,
}: {
  photo: string;
  initials: string;
  name: string;
}) {
  return (
    <div
      className="relative w-20 h-20 overflow-hidden"
      style={{ border: "1px solid var(--color-border)" }}
    >
      <Image
        src={photo}
        alt={name}
        fill
        className="object-cover object-top grayscale"
        onError={(e) => {
          // Hide broken image, show initials fallback via sibling
          (e.currentTarget as HTMLImageElement).style.display = "none";
          const fallback = e.currentTarget.nextElementSibling as HTMLElement;
          if (fallback) fallback.style.display = "flex";
        }}
      />
      {/* Initials fallback — hidden by default, shown if image fails */}
      <div
        className="absolute inset-0 items-center justify-center font-display text-2xl"
        style={{
          display: "none",
          backgroundColor: "rgba(255,255,255,0.03)",
          color: "var(--color-accent)",
        }}
      >
        {initials}
      </div>
    </div>
  );
}

export function AuthorsSection() {
  return (
    <section
      id="authors"
      className="px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      {/* Authors grid */}
      <div className="py-24">
        <div className="flex items-baseline gap-4 mb-16">
          <span
            className="font-mono text-sm"
            style={{ color: "var(--color-accent)" }}
          >
            06
          </span>
          <h2
            className="font-display text-5xl"
            style={{ color: "var(--color-fg)" }}
          >
            AUTHORS
          </h2>
        </div>

        <div
          className="grid grid-cols-1 md:grid-cols-2 gap-px"
          style={{ backgroundColor: "var(--color-border)" }}
        >
          {AUTHORS.map((author) => (
            <div
              key={author.name}
              className="p-8 flex flex-col gap-6"
              style={{ backgroundColor: "var(--color-bg)" }}
            >
              {/* Photo / avatar */}
              <AuthorAvatar
                photo={author.photo}
                initials={author.initials}
                name={author.name}
              />

              {/* Name & title */}
              <div>
                <p
                  className="font-display text-2xl mb-1"
                  style={{ color: "var(--color-fg)" }}
                >
                  {author.name.toUpperCase()}
                </p>
                <p
                  className="font-mono text-sm"
                  style={{ color: "var(--color-muted)" }}
                >
                  {author.title}
                  {author.company && (
                    <>
                      {" "}
                      <span style={{ color: "var(--color-accent)" }}>@</span>{" "}
                      {author.company}
                    </>
                  )}
                </p>
              </div>

              {/* Social links */}
              <div className="flex items-center gap-5">
                <a
                  href={author.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors"
                  style={{ color: "var(--color-muted)" }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLElement).style.color =
                      "var(--color-fg)")
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLElement).style.color =
                      "var(--color-muted)")
                  }
                  aria-label="LinkedIn"
                >
                  <LinkedInIcon />
                </a>
                <a
                  href={author.twitter}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors"
                  style={{ color: "var(--color-muted)" }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLElement).style.color =
                      "var(--color-fg)")
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLElement).style.color =
                      "var(--color-muted)")
                  }
                  aria-label="X / Twitter"
                >
                  <XIcon />
                </a>
                <a
                  href={author.github}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors"
                  style={{ color: "var(--color-muted)" }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLElement).style.color =
                      "var(--color-fg)")
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLElement).style.color =
                      "var(--color-muted)")
                  }
                  aria-label="GitHub"
                >
                  <GitHubIcon />
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div
        className="py-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
        style={{ borderTop: "1px solid var(--color-border)" }}
      >
        <div className="flex items-center gap-4">
          <span
            className="font-display text-2xl"
            style={{ color: "var(--color-fg)" }}
          >
            SYLLOGIC
          </span>
          <span
            className="font-mono text-xs px-2 py-0.5"
            style={{
              border: "1px solid var(--color-border)",
              color: "var(--color-muted)",
            }}
          >
            AGPL-3.0
          </span>
        </div>
        <p
          className="font-mono text-xs"
          style={{ color: "var(--color-muted)" }}
        >
          Open source. Self-hosted. Your data, your rules.
        </p>
      </div>
    </section>
  );
}
