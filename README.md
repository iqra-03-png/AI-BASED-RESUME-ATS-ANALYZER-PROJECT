# ResuNova

ResuNova is a Flask/Jinja resume analyzer with a JavaScript and CSS frontend.

## Run locally

1. Install the Python dependencies with `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and set strong, private values for `SECRET_KEY` and `RESUNOVA_ADMIN_REGISTRATION_KEY`. The app loads `.env` from the project directory; `.env` is ignored by Git.
3. Optionally set `RESUNOVA_ADMIN_EMAIL` and `RESUNOVA_ADMIN_PASSWORD` in `.env` to provision an initial administrator account.
4. From the project directory, start the application with `python app.py`.

The initial admin account is created or promoted from the email/password environment variables when the app starts. Use the Admin toggle on `/auth/login`; ordinary registered accounts cannot authenticate in Admin mode. New admins can register at `/auth/admin/register` only when the server-side invitation key is configured. Admin passwords must be 10-128 characters. The Flask app serves its Jinja frontend directly; Vite is not required to run the website.

The Google sign-in button is a UI placeholder until an OAuth provider is configured.

## Test

Run the backend tests with `pytest`.
