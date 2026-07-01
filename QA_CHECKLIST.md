# QA checklist — cart, requests, and user console

Use this checklist after applying the next milestone implementation.

## Safe command checks

Do not print secrets or full compose output.

```bash
python -m pip install -r requirements-dev.txt
python -m compileall app migrations tests
python -m pytest
docker compose config -q
docker compose up -d --build
curl -f http://localhost/health
```

If Docker is unavailable, run at minimum:

```bash
python -m compileall app migrations tests
python -m pytest
```

## Manual smoke

1. Copy env file: `cp .env.example .env`.
2. Set unique `SECRET_KEY` and strong `ADMIN_PASSWORD`.
3. Add hosts entries if checking Host routing:

   ```text
   127.0.0.1 guru.localhost
   127.0.0.1 knigi.guru.localhost
   ```

4. Open `http://localhost/login` or `http://guru.localhost/login`.
5. Login as admin.
6. Open user console and create an owner user with optional email.
7. Logout and login as that owner. Confirm owner can create storefronts but cannot open the user console.
8. Create storefront `knigi`.
9. Add title, description, and a valid PNG/JPEG/WEBP banner.
10. Add two lots: one finite quantity, one infinite quantity.
11. Confirm public page opens by Host routing: `http://knigi.guru.localhost/`.
12. Confirm dev fallback opens: `http://localhost/s/knigi`.
13. Add a published lot to cart.
14. Try quantity `0`; expect reject.
15. Try quantity above finite available stock; expect reject.
16. Add a valid quantity, open cart, edit quantity, delete item.
17. Add item again and checkout with name/contact/email/comment.
18. Confirm success page.
19. Login as owner/admin and open requests; request must be visible.
20. Open request detail and change status to `confirmed`, then `cancelled`.
21. Open procurement list; only `new`/`confirmed` requests should be aggregated.
22. Create a second owner and storefront; confirm owner A cannot see owner B storefronts or requests.

## Security probes

- POST without `_csrf` should return 403.
- Public user should not open `/requests`, `/procurement`, `/users`, or `/settings`.
- Public cart should not accept a `lot_id` from another storefront.
- Public cart should not accept unpublished lots.
- Upload `.txt` renamed as `.png` with invalid magic bytes should be rejected.
- Path traversal filename like `../x.png` must not control stored file path.
- Production env must reject unsafe `SECRET_KEY` and unsafe default admin password.

## Expected gaps for this milestone

- no real email-code verification yet;
- no durable IP/user-aware rate limit yet;
- no audit log yet;
- no notification adapter yet.
