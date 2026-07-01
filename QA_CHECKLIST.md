# QA checklist — cart, requests, and procurement

Use this checklist after applying the cart/request milestone implementation.

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
6. Create storefront `knigi`.
7. Add title, description, and a valid PNG/JPEG/WEBP banner.
8. Add two lots: one finite quantity, one infinite quantity.
9. Confirm public page opens by Host routing: `http://knigi.guru.localhost/`.
10. Confirm dev fallback opens: `http://localhost/s/knigi`.
11. Add a published lot to cart.
12. Try quantity `0`; expect reject.
13. Try quantity above finite available stock; expect reject.
14. Add a valid quantity, open cart, edit quantity, delete item.
15. Add item again and checkout with name/contact/email/comment.
16. Confirm success page.
17. Login as owner/admin and open requests; request must be visible.
18. Open request detail and change status to `confirmed`, then `cancelled`.
19. Open procurement list; only `new`/`confirmed` requests should be aggregated.
20. Create a second owner directly in DB or fixture and confirm owner A cannot see owner B storefronts or requests.

## Security probes

- Public user should not open `/requests`, `/procurement`, or `/settings`.
- Public cart should not accept a `lot_id` from another storefront.
- Public cart should not accept unpublished lots.
- Public cart should reject quantity `0` and quantity above finite available stock.
- Checkout must not expose buyer PII on public success page.
- Upload `.txt` renamed as `.png` with invalid magic bytes should be rejected.
- Path traversal filename like `../x.png` must not control stored file path.
- Production env must reject unsafe `SECRET_KEY` and unsafe default admin password.

## Known gaps for next security gate

- CSRF protection is still open; do not expect `POST` without `_csrf` to fail until that gate lands.
- no durable IP/user-aware rate limit yet;
- no audit log yet;
- no notification adapter yet;
- no separate owner-management UI yet.
