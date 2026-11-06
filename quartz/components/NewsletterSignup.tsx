import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

interface Options {
  title?: string
  subtitle?: string
  formAction?: string
  buttonText?: string
  placeholder?: string
}

const DEFAULT_WEBHOOK_URL =
  "https://script.google.com/macros/s/AKfycbxKqwM1gUfAdR_-ZZBxtQkDG1yyDYcRwcM9TT6n-MojsgV2muorp9tHM2BgvHsnKZyJ/exec"

const defaults: Options = {
  title: "Sunday Intelligence Briefing",
  subtitle: "Weekly synthesis, data tables & grid telemetry delivered every Sunday at 7:30 PM EST.",
  formAction: DEFAULT_WEBHOOK_URL,
  buttonText: "Subscribe",
  placeholder: "your@email.com",
}

export default ((userOpts?: Options) => {
  const opts = { ...defaults, ...userOpts }
  const actionUrl = opts.formAction || DEFAULT_WEBHOOK_URL

  const NewsletterSignup: QuartzComponent = ({ displayClass }: QuartzComponentProps) => {
    return (
      <div class={`newsletter-signup ${displayClass ?? ""}`}>
        <div class="newsletter-container">
          <h3 class="newsletter-title">{opts.title}</h3>
          <p class="newsletter-subtitle">{opts.subtitle}</p>
          <form class="newsletter-form" action={actionUrl} method="POST" data-webhook={actionUrl}>
            <input type="hidden" name="action" value="nwg_subscribe" />
            <input type="hidden" name="source" value="thenewworldgrid.com" />
            <input
              type="email"
              name="email"
              class="newsletter-input"
              placeholder={opts.placeholder}
              required
              aria-label="Email address"
            />
            <button type="submit" class="newsletter-button">
              {opts.buttonText}
            </button>
          </form>
          <p class="newsletter-status" aria-live="polite"></p>
          <p class="newsletter-privacy">
            Or email <code>anything@thenewworldgrid.com</code> &bull; No spam. Unsubscribe anytime.
          </p>
        </div>
      </div>
    )
  }

  NewsletterSignup.afterDOMLoaded = `
  document.querySelectorAll(".newsletter-form").forEach((formEl) => {
    if (formEl.dataset.bound === "true") return;
    formEl.dataset.bound = "true";
    formEl.addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const input = form.querySelector(".newsletter-input");
      const btn = form.querySelector(".newsletter-button");
      const statusEl = form.parentElement ? form.parentElement.querySelector(".newsletter-status") : null;
      const email = input ? input.value.trim() : "";
      if (!email) return;

      const origText = btn ? btn.textContent : "Subscribe";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Transmitting...";
      }
      if (statusEl) {
        statusEl.textContent = "";
      }

      try {
        const endpoint = form.getAttribute("data-webhook") || form.action;
        const body = new URLSearchParams({
          action: "nwg_subscribe",
          email: email,
          source: "thenewworldgrid.com"
        }).toString();

        await fetch(endpoint, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: body
        });

        if (input) input.value = "";
        if (btn) btn.textContent = "Subscribed ✓";
        if (statusEl) {
          statusEl.textContent = "✓ Locked in for the Sunday Briefing. Check your inbox for confirmation.";
        }
      } catch (err) {
        if (btn) {
          btn.disabled = false;
          btn.textContent = origText;
        }
        if (statusEl) {
          statusEl.textContent = "Transmission error — please try again or email anything@thenewworldgrid.com.";
        }
      }
    });
  });
  `

  NewsletterSignup.css = `
.newsletter-signup {
  width: 100%;
  margin: 3rem auto;
  padding: 2rem 1.5rem;
  background: var(--lightgray);
  border: 1px solid var(--gray);
  border-left: 4px solid var(--secondary);
}

.newsletter-container {
  max-width: 600px;
  margin: 0 auto;
}

.newsletter-title {
  font-family: "Libre Baskerville", serif !important;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--secondary);
  margin: 0 0 0.5rem 0;
  text-transform: uppercase;
  letter-spacing: -0.02em;
}

.newsletter-subtitle {
  font-family: "Source Sans Pro", sans-serif;
  font-size: 0.95rem;
  color: var(--darkgray);
  margin: 0 0 1.5rem 0;
  line-height: 1.5;
}

.newsletter-form {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.newsletter-input {
  flex: 1;
  padding: 0.75rem 1rem;
  background: var(--light);
  border: 1px solid var(--gray);
  color: var(--darkgray);
  font-family: "JetBrains Mono", monospace;
  font-size: 0.9rem;
  outline: none;
  transition: border-color 0.2s ease;
}

.newsletter-input:focus {
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px rgba(0, 255, 65, 0.1);
}

.newsletter-input::placeholder {
  color: var(--gray);
  opacity: 0.7;
}

.newsletter-button {
  padding: 0.75rem 1.5rem;
  background: var(--secondary);
  color: var(--light);
  border: 1px solid var(--secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.newsletter-button:hover {
  background: var(--light);
  color: var(--secondary);
}

.newsletter-status {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.8rem;
  color: var(--secondary);
  margin: 0 0 0.4rem 0;
  text-align: center;
  min-height: 1.1em;
}

.newsletter-privacy {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.75rem;
  color: var(--gray);
  margin: 0;
  text-align: center;
}

.newsletter-placeholder {
  font-family: "JetBrains Mono", monospace;
  font-size: 1rem;
  color: var(--gray);
  text-align: center;
  padding: 1rem;
  border: 1px dashed var(--gray);
}

.terminal-blink {
  animation: nl-blink 1s infinite;
  color: var(--secondary);
}

@keyframes nl-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@media (max-width: 600px) {
  .newsletter-signup {
    padding: 1.5rem 1rem;
    margin: 2rem auto;
  }

  .newsletter-form {
    flex-direction: column;
  }

  .newsletter-button {
    width: 100%;
    padding: 1rem;
    min-height: 48px;
  }

  .newsletter-input {
    min-height: 48px;
  }

  .newsletter-title {
    font-size: 1.2rem;
  }
}
`

  return NewsletterSignup
}) satisfies QuartzComponentConstructor
