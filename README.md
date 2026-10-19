# MedResQ — Medical Resource Finder

MedResQ is a responsive Flask website that helps patients explore a directory of hospitals, blood banks and ambulance services. Patients can search by name or area, filter by category, save entries, suggest additional resources and track their submissions.

## Run on Windows (VS Code / PowerShell)

1. Extract the ZIP and open the `MedResQ_Updated` folder in VS Code.
2. Open **Terminal → New Terminal**. Confirm the terminal is in the folder containing `app.py` and `requirements.txt`.
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Start the website:

   ```powershell
   python app.py
   ```

5. Open <http://127.0.0.1:5000> in your browser. Keep the terminal open while testing.
6. Choose the correct account type on the login page. Patients can create their own account; provider and administrator accounts are included for local evaluation.

## Role-based login for local evaluation

| Account type | Email | Password |
|---|---|---|
| Administrator | `admin@medresq.local` | `Admin@12345` |
| Healthcare provider | `provider@medresq.local` | `Provider@12345` |

Patients can register from the website. Provider and administrator roles are not available through public registration. These credentials are for local project evaluation; change or remove them before any public deployment.

Stop the server with `Ctrl+C` in the terminal.

## Features

- Responsive homepage with a clear patient journey.
- Search by resource name or area and filter by category.
- Resource details in a modal.
- Role-based login for patients, healthcare providers and administrators.
- Patient registration, password hashing, logout, CSRF checks and role-protected workspaces.
- Administrator view of accounts, contact messages and resource suggestions, with suggestion status updates.
- Provider workspace for reviewing directory entries.
- Save and remove directory entries.
- Submit resource suggestions and track their review status.
- Contact form with validation and saved message history for signed-in patients.
- SQLite database created automatically in this folder.

## Directory data and deployment

- The included facility names are **directory preview entries**, not verified real-world provider listings. Before public use, replace them with current information from providers or a trusted directory; do not present preview data as verified medical information.
- Contact form submissions are stored in the local SQLite database. To deliver messages to an email inbox, configure an email provider.
- For emergencies in India, call **112**. Confirm a provider’s current address, services and availability directly.
- Before public deployment, configure a strong persistent `MEDRESQ_SECRET_KEY`, enable HTTPS, add rate limiting and account recovery, and review privacy/security requirements. Do not collect patient medical records in this project.

## Project structure

```text
MedResQ_Updated/
├── app.py
├── requirements.txt
├── README.md
├── static/
│   └── style.css
└── templates/
    ├── auth.html
    ├── admin_dashboard.html
    ├── provider_dashboard.html
    ├── contact.html
    ├── dashboard.html
    ├── error.html
    └── index.html
```
