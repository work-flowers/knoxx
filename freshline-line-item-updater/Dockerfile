FROM apify/actor-node-puppeteer-chrome:22

# Copy package files with correct ownership
COPY --chown=myuser:myuser package*.json ./

# Install dependencies
RUN npm --quiet set progress=false \
    && npm ci --omit=dev \
    && echo "Installed NPM packages:" \
    && (npm list --depth=0 || true) \
    && echo "Node.js version:" \
    && node --version \
    && echo "NPM version:" \
    && npm --version

# Copy source code
COPY --chown=myuser:myuser . ./

# Run the actor
CMD npm start
