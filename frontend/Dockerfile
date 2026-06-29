FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . ./

EXPOSE 3000
# 开发模式(脚手架阶段);上线再换成 build + start
CMD ["npm", "run", "dev"]
