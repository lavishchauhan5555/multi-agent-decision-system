/**
 * middleware/errorHandler.js
 * ───────────────────────────
 * Global Express error handler.
 * Mount LAST in app.js after all routes.
 */

const errorHandler = (err, req, res, next) => {
  console.error('[Error]', err.message);

  const status  = err.status || err.statusCode || 500;
  const message = err.message || 'Internal server error';

  res.status(status).json({
    error:   message,
    path:    req.path,
    method:  req.method,
  });
};

export default errorHandler;