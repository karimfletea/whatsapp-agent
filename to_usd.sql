UPDATE businesses SET currency='USD' WHERE id=1;
UPDATE products SET price_cents=600 WHERE id=1;
UPDATE products SET price_cents=850 WHERE id=2;
UPDATE products SET price_cents=300 WHERE id=3;
UPDATE products SET price_cents=150 WHERE id=4;
UPDATE products SET price_cents=900 WHERE id=5;
SELECT id, name, currency FROM businesses;
SELECT id, name, price_cents FROM products WHERE business_id=1;
