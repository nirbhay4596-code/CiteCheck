# Request for Indian Kanoon's non-commercial API credit

Indian Kanoon gives non-commercial projects ₹10,000 of API credit a month once they have verified the use case. Send this from nirbhay4596@gmail.com, the address the API account is registered under, using the contact details on [api.indiankanoon.org](https://api.indiankanoon.org/). Only the phone number is left to fill in.

---

**Subject:** Non-commercial API credit for CiteCheck, an open-source citation checker

Dear Indian Kanoon team,

I am Nirbhay Gupta, an advocate enrolled with the Bar Council of Delhi. I have built CiteCheck, a free and open-source tool that checks the case citations and quotations in a draft pleading against Indian Kanoon before it is filed.

Courts have begun to see filings that cite judgments which do not exist, or quote passages that are not in the judgment cited. CiteCheck reads a draft, finds every citation and quotation, and confirms each one against Indian Kanoon. Every result links back to the judgment on indiankanoon.org.

- Source code: https://github.com/nirbhay4596-code/CiteCheck
- Public demo: https://citecheck.streamlit.app
- API account: nirbhay4596@gmail.com

The project is non-commercial: there is no charge, no advertising and no paid tier. Every set of results displays your "powered by IKanoon" graphic on top, as your API terms require, and states that the tool is independent and not endorsed by Indian Kanoon. To keep usage modest:

- every API response is cached, so checking the same draft again makes no new calls;
- the public demo runs on a small offline library of saved judgments and makes no API calls at all;
- when live checking is enabled it is capped at 50 calls a day;
- a typical draft needs 10 to 30 calls (search and document requests only).

I would be grateful if you could consider the account for non-commercial credit. I am happy to change how the tool uses the API if you would prefer it to work differently.

Thank you for making Indian law accessible.

Regards,
Nirbhay Gupta
Advocate, Bar Council of Delhi
[phone]
